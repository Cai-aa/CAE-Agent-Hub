# Makefile for Sphinx documentation

SPHINXOPTS    ?= -W --keep-going
SPHINXBUILD   ?= sphinx-build
PAPER         ?=
SOURCEDIR     ?= source
BUILDDIR      ?= _build
AUTOAPIDIR	  ?= source/api

PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS)
SPHINXSRCDIR    = $(SOURCEDIR)

.PHONY: help clean html pdf linkcheck

help:
	@$(SPHINXBUILD) -M help "$(SPHINXSRCDIR)" "$(BUILDDIR)" $(ALLSPHINXOPTS) $(O)

clean:
	rm -rf $(BUILDDIR)/*
	rm -rf $(AUTOAPIDIR)/*

html:
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) "$(SPHINXSRCDIR)" $(BUILDDIR)/html
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."

pdf:
	$(SPHINXBUILD) -M latexpdf "$(SPHINXSRCDIR)" "$(BUILDDIR)" $(ALLSPHINXOPTS) $(O)
	@echo
	@echo "Build finished. The PDF files are in $(BUILDDIR)/latex."

linkcheck:
	@$(SPHINXBUILD) -b linkcheck $(ALLSPHINXOPTS) "$(SPHINXSRCDIR)" $(BUILDDIR)/linkcheck

.DEFAULT_GOAL := help
