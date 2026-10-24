// Package r2 stores and serves files on Cloudflare R2 (MinIO locally). Both speak the S3 protocol.
// The website never gets direct access: the API hands out short-lived view links only to the owner.
package r2

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type Store struct {
	client *minio.Client
	viewer *minio.Client // signs view links with the address a browser can reach
	bucket string
	ttl    time.Duration
}

type Options struct {
	Endpoint    string // full address, for example http://minio:9000
	Region      string
	Bucket      string
	AccessKey   string
	SecretKey   string
	ViewLinkTTL time.Duration
	// PublicEndpoint is the address a browser can reach, used only to sign view links. Empty means the same as
	// Endpoint (right when the storage is already public, as R2 is; inside Docker the two differ).
	PublicEndpoint string
}

func New(o Options) (*Store, error) {
	u, err := url.Parse(o.Endpoint)
	if err != nil || u.Host == "" {
		return nil, fmt.Errorf("storage endpoint %q is not a full address", o.Endpoint)
	}
	client, err := minio.New(u.Host, &minio.Options{
		Creds:  credentials.NewStaticV4(o.AccessKey, o.SecretKey, ""),
		Secure: u.Scheme == "https",
		Region: o.Region,
	})
	if err != nil {
		return nil, fmt.Errorf("open storage client: %w", err)
	}
	viewer := client
	if o.PublicEndpoint != "" && o.PublicEndpoint != o.Endpoint {
		pu, err := url.Parse(o.PublicEndpoint)
		if err != nil || pu.Host == "" {
			return nil, fmt.Errorf("public storage address %q is not a full address", o.PublicEndpoint)
		}
		viewer, err = minio.New(pu.Host, &minio.Options{
			Creds:  credentials.NewStaticV4(o.AccessKey, o.SecretKey, ""),
			Secure: pu.Scheme == "https",
			Region: o.Region, // set, so signing needs no network call to the public address
		})
		if err != nil {
			return nil, fmt.Errorf("open public storage client: %w", err)
		}
	}
	return &Store{client: client, viewer: viewer, bucket: o.Bucket, ttl: o.ViewLinkTTL}, nil
}

// EnsureBucket creates the bucket if it does not exist yet.
func (s *Store) EnsureBucket(ctx context.Context) error {
	exists, err := s.client.BucketExists(ctx, s.bucket)
	if err != nil {
		return fmt.Errorf("check bucket: %w", err)
	}
	if exists {
		return nil
	}
	if err := s.client.MakeBucket(ctx, s.bucket, minio.MakeBucketOptions{}); err != nil {
		return fmt.Errorf("create bucket: %w", err)
	}
	return nil
}

// Put uploads a file. Pass size -1 when the length is not known.
func (s *Store) Put(ctx context.Context, key string, r io.Reader, size int64, contentType string) error {
	_, err := s.client.PutObject(ctx, s.bucket, key, r, size, minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		return fmt.Errorf("upload %s: %w", key, err)
	}
	return nil
}

// Get opens a file. The caller closes it.
func (s *Store) Get(ctx context.Context, key string) (io.ReadCloser, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", key, err)
	}
	if _, err := obj.Stat(); err != nil {
		_ = obj.Close()
		return nil, fmt.Errorf("open %s: %w", key, err)
	}
	return obj, nil
}

// Delete removes one file. Removing a file that is not there is not an error.
func (s *Store) Delete(ctx context.Context, key string) error {
	if err := s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{}); err != nil {
		return fmt.Errorf("delete %s: %w", key, err)
	}
	return nil
}

// DeletePrefix removes every file under a folder, for example all of a candidate's resumes.
func (s *Store) DeletePrefix(ctx context.Context, prefix string) error {
	for obj := range s.client.ListObjects(ctx, s.bucket, minio.ListObjectsOptions{Prefix: prefix, Recursive: true}) {
		if obj.Err != nil {
			return fmt.Errorf("list %s: %w", prefix, obj.Err)
		}
		if err := s.Delete(ctx, obj.Key); err != nil {
			return err
		}
	}
	return nil
}

// ViewLink returns a short-lived address for viewing one file. Give it only to the owner.
func (s *Store) ViewLink(ctx context.Context, key string) (string, error) {
	u, err := s.viewer.PresignedGetObject(ctx, s.bucket, key, s.ttl, nil)
	if err != nil {
		return "", fmt.Errorf("make view link for %s: %w", key, err)
	}
	return u.String(), nil
}
