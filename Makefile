PREFIX ?= /usr/local
SHAREDIR ?= $(PREFIX)/share/scnet-aichat

.PHONY: test install uninstall

test:
	./tests/test.sh

install:
	install -d "$(DESTDIR)$(PREFIX)/bin" "$(DESTDIR)$(SHAREDIR)" \
		"$(DESTDIR)$(SHAREDIR)/worker" "$(DESTDIR)$(SHAREDIR)/server"
	install -m 755 scnet-aichat "$(DESTDIR)$(PREFIX)/bin/scnet-aichat"
	install -m 755 install.sh uninstall.sh "$(DESTDIR)$(SHAREDIR)/"
	install -m 755 worker/scnet-aichat-worker.slurm "$(DESTDIR)$(SHAREDIR)/worker/scnet-aichat-worker.slurm"
	install -m 755 server/llama-server.slurm server/build-server.sh server/start-server.sh "$(DESTDIR)$(SHAREDIR)/server/"
	install -m 644 config.example "$(DESTDIR)$(SHAREDIR)/config.example"

uninstall:
	rm -f "$(DESTDIR)$(PREFIX)/bin/scnet-aichat"
	rm -rf "$(DESTDIR)$(SHAREDIR)"
