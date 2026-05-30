/**
 * Minimal next/server mock for middleware unit tests.
 * Only implements what middleware.ts actually uses.
 */

export class NextResponse {
  readonly status: number;
  readonly headers: Map<string, string>;
  readonly cookies: { set: (name: string, value: string, opts?: object) => void };
  private _cookies: Map<string, string> = new Map();

  constructor(body: null, init: { status: number; headers?: Record<string, string> }) {
    this.status = init.status;
    this.headers = new Map(Object.entries(init.headers ?? {}));
    this.cookies = {
      set: (name: string, value: string) => {
        this._cookies.set(name, value);
      },
    };
  }

  getCookie(name: string): string | undefined {
    return this._cookies.get(name);
  }

  static redirect(url: URL | string, init?: { status?: number }) {
    const res = new NextResponse(null, { status: init?.status ?? 307 });
    res.headers.set("location", url.toString());
    return res;
  }

  static next() {
    return new NextResponse(null, { status: 200 });
  }
}

export class NextRequest {
  readonly url: string;
  readonly nextUrl: URL;
  readonly cookies: { get: (name: string) => { value: string } | undefined };

  constructor(url: string, cookies: Record<string, string> = {}) {
    this.url = url;
    this.nextUrl = new URL(url);
    this.cookies = {
      get: (name: string) =>
        name in cookies ? { value: cookies[name] } : undefined,
    };
  }
}
