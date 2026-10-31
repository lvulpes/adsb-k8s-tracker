#!/usr/bin/env bash

if [[ "$1" == "--reg" ]]; then
    AIRCRAFT=$2
    ENDPOINT="registration"
elif [[ "$1" == "--hex" ]]; then
    AIRCRAFT=$2
    ENDPOINT="hex"
else
    echo "--reg or --hex must be supplied"
fi

BASE_URL="https://opendata.adsb.fi/api/v2"

curl -s "$BASE_URL/$ENDPOINT/$AIRCRAFT" | yq -P '.ac | map({"hex": .hex, "reg": .r, "type": .t, "comment": .desc})'
