# sudo make install
# make install DESTDIR=pkg PREFIX=/usr

NAME = deepcool-lcd
APP_ID = io.github.zazazaxky_m.DeepCoolLCD
VERSION = $(shell sed -n "s/^__version__ = '\(.*\)'/\1/p" deepcool_lcd/__init__.py)

PREFIX ?= /usr/local
DESTDIR ?=
PYTHON ?= /usr/bin/python3
BINDIR ?= $(PREFIX)/bin
LIBDIR ?= $(PREFIX)/lib/$(NAME)
DATADIR ?= $(PREFIX)/share
SYSTEMD_UNIT_DIR ?= $(PREFIX)/lib/systemd/system
# udev and systemd-sysusers only read /usr/lib and /etc
ifeq ($(PREFIX),/usr)
UDEV_RULES_DIR ?= /usr/lib/udev/rules.d
SYSUSERS_DIR ?= /usr/lib/sysusers.d
else
UDEV_RULES_DIR ?= /etc/udev/rules.d
SYSUSERS_DIR ?= /etc/sysusers.d
endif

.PHONY: all install setup uninstall test screenshots dist

all:
	@echo "Nothing to build. Run 'sudo make install', or 'make test'."

install:
	install -d $(DESTDIR)$(LIBDIR)/deepcool_lcd
	install -m644 deepcool_lcd/*.py $(DESTDIR)$(LIBDIR)/deepcool_lcd/
	echo "DATA_DIR = '$(DATADIR)/$(NAME)'" > $(DESTDIR)$(LIBDIR)/deepcool_lcd/_build_paths.py
	install -d $(DESTDIR)$(BINDIR)
	sed -e 's|@PYTHON@|$(PYTHON)|' -e 's|@LIBDIR@|$(LIBDIR)|' -e 's|@MODULE@|cli|' data/launcher.in > $(DESTDIR)$(BINDIR)/$(NAME)
	sed -e 's|@PYTHON@|$(PYTHON)|' -e 's|@LIBDIR@|$(LIBDIR)|' -e 's|@MODULE@|studio|' data/launcher.in > $(DESTDIR)$(BINDIR)/$(NAME)-studio
	chmod 755 $(DESTDIR)$(BINDIR)/$(NAME) $(DESTDIR)$(BINDIR)/$(NAME)-studio
	install -d $(DESTDIR)$(DATADIR)/$(NAME)/fonts
	install -m644 data/fonts/* $(DESTDIR)$(DATADIR)/$(NAME)/fonts/
	install -d $(DESTDIR)$(SYSTEMD_UNIT_DIR)
	sed -e 's|@BINDIR@|$(BINDIR)|' data/$(NAME).service.in > $(DESTDIR)$(SYSTEMD_UNIT_DIR)/$(NAME).service
	chmod 644 $(DESTDIR)$(SYSTEMD_UNIT_DIR)/$(NAME).service
	install -Dm644 data/60-$(NAME).rules $(DESTDIR)$(UDEV_RULES_DIR)/60-$(NAME).rules
	install -Dm644 data/$(NAME).sysusers $(DESTDIR)$(SYSUSERS_DIR)/$(NAME).conf
	install -Dm644 data/$(APP_ID).desktop $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	install -Dm644 data/$(APP_ID).metainfo.xml $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	install -Dm644 data/$(APP_ID).svg $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -Dm644 LICENSE $(DESTDIR)$(DATADIR)/doc/$(NAME)/LICENSE
	install -Dm644 README.md $(DESTDIR)$(DATADIR)/doc/$(NAME)/README.md
	@if [ -z "$(DESTDIR)" ]; then $(MAKE) --no-print-directory setup; fi

setup:
	systemd-sysusers $(SYSUSERS_DIR)/$(NAME).conf
	udevadm control --reload
	udevadm trigger --subsystem-match=usb --attr-match=idVendor=3633 --action=add
	udevadm trigger --subsystem-match=powercap --action=add
	systemctl daemon-reload
	@echo
	@echo "Installed DeepCool LCD $(VERSION). Start it with:"
	@echo "  sudo systemctl enable --now $(NAME)"
	@echo "then open 'DeepCool LCD Studio' from your app menu."

uninstall:
	-systemctl disable --now $(NAME) 2>/dev/null
	rm -rf $(DESTDIR)$(LIBDIR) $(DESTDIR)$(DATADIR)/$(NAME) $(DESTDIR)$(DATADIR)/doc/$(NAME)
	rm -f $(DESTDIR)$(BINDIR)/$(NAME) $(DESTDIR)$(BINDIR)/$(NAME)-studio
	rm -f $(DESTDIR)$(SYSTEMD_UNIT_DIR)/$(NAME).service
	rm -f $(DESTDIR)$(UDEV_RULES_DIR)/60-$(NAME).rules $(DESTDIR)$(SYSUSERS_DIR)/$(NAME).conf
	rm -f $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	-[ -z "$(DESTDIR)" ] && systemctl daemon-reload && udevadm control --reload
	@echo "Removed. Your settings stay in /etc/$(NAME)/ (delete it to start fresh)."

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

screenshots:
	$(PYTHON) tools/render_gallery.py docs/screenshots

dist:
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ -o $(NAME)-$(VERSION).tar.gz HEAD
