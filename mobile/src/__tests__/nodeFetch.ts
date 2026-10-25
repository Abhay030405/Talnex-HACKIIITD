import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';

/** jest-expo swaps the global fetch for a mock, so tests that need real HTTP use this small one. */
export function nodeFetch(url: string, init: RequestInit): Promise<{ status: number }> {
  const request = url.startsWith('https:') ? httpsRequest : httpRequest;
  return new Promise((resolve, reject) => {
    const req = request(
      url,
      { method: init.method, headers: init.headers as Record<string, string>, signal: init.signal ?? undefined },
      (res) => {
        res.resume();
        res.on('end', () => resolve({ status: res.statusCode ?? 0 }));
      },
    );
    req.on('error', reject);
    req.end(init.body as string);
  });
}
