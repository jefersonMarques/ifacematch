SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

VERSION ?= 0.1.12
BASE_ARCHIVE ?=
ARCHIVE ?=
GIT_PROTOCOL ?= ssh

export GIT_PROTOCOL

.PHONY: help doctor bootstrap test-coordinator test build release-base release release-verify publish deploy

help:
	@python3 scripts/coordinator.py help

doctor:
	@python3 scripts/coordinator.py doctor

bootstrap:
	@python3 scripts/coordinator.py bootstrap

test-coordinator:
	@python3 -m unittest discover -s tests -v

test: test-coordinator
	@python3 scripts/coordinator.py test

build:
	@python3 scripts/coordinator.py build

release-base:
	@python3 scripts/coordinator.py release-base --base-archive "$(BASE_ARCHIVE)"

release:
	@python3 scripts/coordinator.py release --version "$(VERSION)" --base-archive "$(BASE_ARCHIVE)"

release-verify:
	@python3 scripts/coordinator.py release-verify --version "$(VERSION)" --archive "$(ARCHIVE)"

publish:
	@python3 scripts/coordinator.py publish --version "$(VERSION)" --archive "$(ARCHIVE)"

deploy:
	@python3 scripts/coordinator.py deploy --version "$(VERSION)" --archive "$(ARCHIVE)"
