PREFIX ?= /usr/local
SHAREDIR ?= $(PREFIX)/share/scnet-aichat

.PHONY: test install uninstall

test:
	./tests/test.sh

install:
	install -d "$(DESTDIR)$(PREFIX)/bin" "$(DESTDIR)$(SHAREDIR)"
	install -m 755 scnet-aichat "$(DESTDIR)$(PREFIX)/bin/scnet-aichat"
	install -m 755 worker/scnet-aichat-worker.slurm "$(DESTDIR)$(SHAREDIR)/scnet-aichat-worker.slurm"

uninstall:
	rm -f "$(DESTDIR)$(PREFIX)/bin/scnet-aichat"
	rm -f "$(DESTDIR)$(SHAREDIR)/scnet-aichat-worker.slurm"
