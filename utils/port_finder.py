"""Find a free TCP port in a range (optional dev helper)."""
import socket


def find_free_port(start_port: int = 8085, end_port: int = 8150) -> int:
    """Return the first port in [start_port, end_port] that accepts a bind, or start_port on failure."""
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return start_port
