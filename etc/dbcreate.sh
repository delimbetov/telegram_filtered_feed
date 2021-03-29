#!/bin/bash

echo "Dropping db feed"
dropdb --if-exists feed

echo "Creating db feed"
createdb feed

echo "Creating schema"
psql -f ./etc/schema.sql feed
