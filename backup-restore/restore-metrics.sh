#/bin/sh

# this file will be run on the victoriametrics/vmrestore image
# see the "export-metrics" makefile target for usage
#   - note the metrics data mount at /storage
#   - note the host mount at /host
#   - note we're in the conn-probe-network network, so we can access the victoriametrics HTTP snapshot API

# the out-of-the-box behavior is vmbackup is to dump the backup into the dst directory
# this command builds on that by tar-ing the directory, and then nicely placing it on the host

tar -xzvf "/host/metrics.tar.gz" -C "/"

/./vmrestore-prod \
    -storageDataPath "/storage" \
    -src "fs:///backup"
