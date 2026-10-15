.PHONY: help test test-install test-cli lint validate gitleaks install uninstall check

SHELLSPEC ?= shellspec

help:
	@echo "DevSkills - comandos de desarrollo"
	@echo ""
	@echo "Uso: make [objetivo]"
	@echo ""
	@echo "  test          Corre todas las pruebas (ShellSpec)"
	@echo "  test-install  Pruebas de install.sh y uninstall.sh"
	@echo "  test-cli      Pruebas del CLI devskills"
	@echo "  lint          ShellCheck sobre el CLI, los instaladores y las pruebas"
	@echo "  validate      Valida el plugin y el marketplace (claude plugin validate)"
	@echo "  gitleaks      Busca secretos con gitleaks (nativo; Docker como alternativa)"
	@echo "  install       Instala DevSkills en tu usuario (install.sh)"
	@echo "  uninstall     Quita lo instalado (uninstall.sh)"
	@echo "  check         lint + validate + test"
	@echo ""

test:
	$(SHELLSPEC)

test-install:
	$(SHELLSPEC) spec/integration/install_spec.sh

test-cli:
	$(SHELLSPEC) spec/integration/cli_spec.sh

lint:
	shellcheck -x -e SC1090,SC1091 bin/devskills install.sh uninstall.sh hooks/vetar_acciones_externas.sh
	shellcheck -x -e SC1090,SC1091,SC2034,SC2154,SC2329 spec/spec_helper.sh

validate:
	claude plugin validate .

gitleaks:
	python scripts/gitleaks_archivos.py

install:
	bash install.sh

uninstall:
	bash uninstall.sh

check: lint validate test
