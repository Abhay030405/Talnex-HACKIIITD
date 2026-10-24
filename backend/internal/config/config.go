// Package config is the one place in the Go backend that reads environment settings.
// A missing required setting stops the service with a message naming it (AGENTS.md section 5).
package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Database struct {
	URL string
}

type Storage struct {
	Endpoint    string
	Region      string
	Bucket      string
	AccessKey   string
	SecretKey   string
	ViewLinkTTL time.Duration
	// PublicEndpoint: where a browser reaches the storage (for screenshot links). Empty = same as Endpoint.
	PublicEndpoint string
}

type API struct {
	Port               int
	AuthSecret         string
	WebOrigin          string
	EnableDevEndpoints bool
	// SMSGatewayKey is optional: empty switches phone sign-up off.
	SMSGatewayKey string
	Walkthrough   Walkthrough
}

type Worker struct {
	Concurrency  int
	HealthPort   int
	PollInterval time.Duration
	ReapInterval time.Duration
	RetryDelay   time.Duration
}

type GitHub struct {
	BaseURL string
	Token   string
	History GitHubHistory
}

// GitHubHistory caps how much history the authorship stage reads per project (architecture section 30.4).
type GitHubHistory struct {
	FilesPerClaim    int
	ClaimsPerProject int
	CommitsPerFile   int
	BranchCommits    int
}

// Walkthrough limits the voice walkthrough questions (architecture section 31).
type Walkthrough struct {
	AudioMaxBytes   int
	QuestionsPerDay int
}

type Codeforces struct {
	BaseURL string
}

type Migrate struct {
	Dir string
}

type Config struct {
	Database   Database
	Storage    Storage
	API        API
	Worker     Worker
	GitHub     GitHub
	Codeforces Codeforces
	Migrate    Migrate
}

// reader collects every problem so one start-up message lists all of them.
type reader struct {
	missing []string
	invalid []string
}

func (r *reader) required(name string) string {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		r.missing = append(r.missing, name)
	}
	return v
}

func (r *reader) integer(name string, def int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return def
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		r.invalid = append(r.invalid, name+" must be a positive whole number")
		return def
	}
	return n
}

func (r *reader) boolean(name string) bool {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return false
	}
	b, err := strconv.ParseBool(raw)
	if err != nil {
		r.invalid = append(r.invalid, name+" must be true or false")
	}
	return b
}

func (r *reader) err() error {
	if len(r.missing) == 0 && len(r.invalid) == 0 {
		return nil
	}
	var parts []string
	if len(r.missing) > 0 {
		parts = append(parts, "missing required settings: "+strings.Join(r.missing, ", "))
	}
	parts = append(parts, r.invalid...)
	return fmt.Errorf("%s (see .env.example)", strings.Join(parts, "; "))
}

func (r *reader) database(c *Config) {
	c.Database.URL = r.required("DATABASE_URL")
}

func (r *reader) storage(c *Config) {
	c.Storage = Storage{
		Endpoint:       r.required("S3_ENDPOINT"),
		Region:         r.required("S3_REGION"),
		Bucket:         r.required("S3_BUCKET"),
		AccessKey:      r.required("S3_ACCESS_KEY"),
		SecretKey:      r.required("S3_SECRET_KEY"),
		ViewLinkTTL:    time.Duration(r.integer("S3_VIEW_LINK_TTL_SECONDS", 300)) * time.Second,
		PublicEndpoint: strings.TrimSpace(os.Getenv("S3_PUBLIC_ENDPOINT")),
	}
	if c.Storage.Endpoint != "" {
		if u, err := url.Parse(c.Storage.Endpoint); err != nil || u.Host == "" {
			r.invalid = append(r.invalid, "S3_ENDPOINT must be a full address like http://minio:9000")
		}
	}
}

// LoadAPI reads what the API server needs.
func LoadAPI() (*Config, error) {
	r := &reader{}
	c := &Config{}
	r.database(c)
	r.storage(c)
	c.API = API{
		Port:               r.integer("API_PORT", 8080),
		AuthSecret:         r.required("AUTH_SECRET"),
		WebOrigin:          r.required("WEB_ORIGIN"),
		EnableDevEndpoints: r.boolean("ENABLE_DEV_ENDPOINTS"),
		SMSGatewayKey:      strings.TrimSpace(os.Getenv("SMS_GATEWAY_KEY")),
		Walkthrough: Walkthrough{
			AudioMaxBytes:   r.integer("WALKTHROUGH_AUDIO_MAX_BYTES", 10<<20),
			QuestionsPerDay: r.integer("WALKTHROUGH_QUESTIONS_PER_DAY", 30),
		},
	}
	if c.API.SMSGatewayKey != "" && len(c.API.SMSGatewayKey) < 16 {
		r.invalid = append(r.invalid, "SMS_GATEWAY_KEY must be at least 16 characters (or empty to switch phone sign-up off)")
	}
	if c.API.AuthSecret != "" && len(c.API.AuthSecret) < 16 {
		r.invalid = append(r.invalid, "AUTH_SECRET must be at least 16 characters")
	}
	return c, r.err()
}

// LoadWorker reads what the Go workers need.
func LoadWorker() (*Config, error) {
	r := &reader{}
	c := &Config{}
	r.database(c)
	r.storage(c)
	c.Worker = Worker{
		Concurrency:  r.integer("GO_WORKER_CONCURRENCY", 4),
		HealthPort:   r.integer("GO_WORKER_HEALTH_PORT", 8081),
		PollInterval: time.Duration(r.integer("JOB_POLL_SECONDS", 5)) * time.Second,
		ReapInterval: time.Duration(r.integer("JOB_REAP_SECONDS", 30)) * time.Second,
		RetryDelay:   time.Duration(r.integer("JOB_RETRY_DELAY_SECONDS", 30)) * time.Second,
	}
	c.GitHub = GitHub{BaseURL: r.required("GITHUB_API_BASE_URL"), Token: r.required("GITHUB_TOKEN"),
		History: GitHubHistory{
			FilesPerClaim:    r.integer("GITHUB_HISTORY_FILES_PER_CLAIM", 15),
			ClaimsPerProject: r.integer("GITHUB_HISTORY_CLAIMS_PER_PROJECT", 40),
			CommitsPerFile:   r.integer("GITHUB_HISTORY_COMMITS_PER_FILE", 100),
			BranchCommits:    r.integer("GITHUB_HISTORY_BRANCH_COMMITS", 1000),
		}}
	if c.GitHub.BaseURL != "" {
		if u, err := url.Parse(c.GitHub.BaseURL); err != nil || u.Host == "" {
			r.invalid = append(r.invalid, "GITHUB_API_BASE_URL must be a full address like https://api.github.com")
		}
	}
	c.Codeforces = Codeforces{BaseURL: r.required("CODEFORCES_API_BASE_URL")}
	if c.Codeforces.BaseURL != "" {
		if u, err := url.Parse(c.Codeforces.BaseURL); err != nil || u.Host == "" {
			r.invalid = append(r.invalid, "CODEFORCES_API_BASE_URL must be a full address like https://codeforces.com/api")
		}
	}
	return c, r.err()
}

// LoadMigrate reads what the migration runner needs.
func LoadMigrate() (*Config, error) {
	r := &reader{}
	c := &Config{}
	r.database(c)
	c.Migrate.Dir = r.required("MIGRATIONS_DIR")
	return c, r.err()
}
