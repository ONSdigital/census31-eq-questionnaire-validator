#!/usr/bin/env bash

printf "%s" "$(git rev-parse HEAD)" >.application-version
