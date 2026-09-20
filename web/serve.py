"""Loopback development server for the adjacent Nau web package (Python 3)."""
import argparse
import http.server
import pathlib
import socket
import sys
import urllib.parse


class PackageServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class PackageHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.wasm': 'application/wasm'}

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def send_head(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if not path.startswith(self.server.base_path):
            self.send_error(404, 'Outside package URL base')
            return None
        relative = path[len(self.server.base_path):]
        if '\\' in relative or any(part in ('.', '..') for part in relative.split('/')):
            self.send_error(403, 'Package traversal rejected')
            return None
        target = (self.server.package_root / relative).resolve()
        if target.is_dir():
            for name in ('index.html', 'index.htm'):
                index = target / name
                if index.exists():
                    target = index.resolve()
                    break
        if not target.is_relative_to(self.server.package_root):
            self.send_error(403, 'Outside package root')
            return None
        self.package_target = target
        return super().send_head()

    def translate_path(self, path):
        return str(self.package_target)

    def list_directory(self, path):
        self.send_error(403, 'Directory listing disabled')
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--base-path', default='/')
    args = parser.parse_args()
    parts = args.base_path.strip('/').split('/') if args.base_path.strip('/') else []
    if any(not part or part in ('.', '..') or not all(c.isalnum() or c in '-_' for c in part) for part in parts):
        parser.error('--base-path must contain simple URL directory names')
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    base = '/' + '/'.join(parts) + ('/' if parts else '')
    try:
        with PackageServer(('127.0.0.1', args.port), PackageHandler) as server:
            server.package_root = pathlib.Path(__file__).resolve().parent
            server.base_path = base
            print(f'http://127.0.0.1:{server.server_port}{base}', flush=True)
            server.serve_forever()
    except OSError as error:
        print(f'Cannot serve on port {args.port}: {error}. Choose another --port.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
