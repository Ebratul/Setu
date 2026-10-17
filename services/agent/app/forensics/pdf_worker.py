"""Child process that parses one PDF under hard resource limits (see sandbox.py).

python -m app.forensics.pdf_worker <memory MB> <cpu seconds>   (PDF bytes on stdin, JSON out)
"""

import json
import resource
import sys


def main() -> int:
    memory_mb, cpu_s = int(sys.argv[1]), int(sys.argv[2])
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb << 20, memory_mb << 20))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # the parser writes nothing
    data = sys.stdin.buffer.read()
    from app.forensics.pdf_text import read_pdf, to_dict

    sys.stdout.write(json.dumps(to_dict(read_pdf(data))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
