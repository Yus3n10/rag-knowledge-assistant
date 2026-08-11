#!/usr/bin/env bash
# Retries an Oracle Cloud free-tier ARM (Ampere A1) instance launch until
# capacity is available. Free-tier ARM capacity is frequently exhausted in
# popular regions -- "Out of host capacity" here is normal, not a misconfig.
#
# Prereqs (one-time, manual):
#   1. oci setup config   -- needs an API key uploaded to the OCI console
#      plus your tenancy/user OCIDs; the CLI walks you through it.
#   2. Fill in the OCIDs below (see the "how to find these" comments).
set -euo pipefail

COMPARTMENT_ID="${COMPARTMENT_ID:?set COMPARTMENT_ID}"
AVAILABILITY_DOMAIN="${AVAILABILITY_DOMAIN:?set AVAILABILITY_DOMAIN}"    # oci iam availability-domain list
SUBNET_ID="${SUBNET_ID:?set SUBNET_ID}"                                  # oci network subnet list --compartment-id $COMPARTMENT_ID
IMAGE_ID="${IMAGE_ID:?set IMAGE_ID}"                                     # oci compute image list --compartment-id $COMPARTMENT_ID --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape "VM.Standard.A1.Flex"
SSH_KEY_FILE="${SSH_KEY_FILE:-$HOME/.ssh/id_rsa.pub}"
DISPLAY_NAME="${DISPLAY_NAME:-rag-knowledge-assistant}"
OCPUS="${OCPUS:-4}"
MEMORY_GB="${MEMORY_GB:-24}"
RETRY_SECONDS="${RETRY_SECONDS:-60}"

echo "Launching $DISPLAY_NAME ($OCPUS OCPU / ${MEMORY_GB}GB) in $AVAILABILITY_DOMAIN -- retrying every ${RETRY_SECONDS}s until capacity is available. Ctrl+C to stop."

attempt=0
while true; do
  attempt=$((attempt + 1))
  echo "[$(date '+%H:%M:%S')] attempt $attempt"

  if output=$(oci compute instance launch \
    --compartment-id "$COMPARTMENT_ID" \
    --availability-domain "$AVAILABILITY_DOMAIN" \
    --shape "VM.Standard.A1.Flex" \
    --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEMORY_GB}" \
    --image-id "$IMAGE_ID" \
    --subnet-id "$SUBNET_ID" \
    --assign-public-ip true \
    --display-name "$DISPLAY_NAME" \
    --ssh-authorized-keys-file "$SSH_KEY_FILE" \
    2>&1); then
    echo "$output"
    echo "Launched."
    break
  fi

  if echo "$output" | grep -qi "out of host capacity\|OutOfCapacity"; then
    echo "  out of capacity, retrying in ${RETRY_SECONDS}s..."
    sleep "$RETRY_SECONDS"
  else
    echo "$output"
    echo "Non-capacity error, stopping."
    exit 1
  fi
done
