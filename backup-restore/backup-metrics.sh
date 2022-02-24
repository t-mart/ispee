#/bin/sh

# this file will be run on the victoriametrics/vmbackup image
# see the "export-metrics" makefile target for usage
#   - note the metrics data mount at /storage
#   - note the host mount at /host
#   - note we're in the conn-probe-network network, so we can access the victoriametrics HTTP snapshot API

# the out-of-the-box behavior is vmbackup is to dump the backup into the -dst directory.
# this command builds on that by tar-ing the directory, and then nicely placing it on the host

mkdir /backup

/./vmbackup-prod \
    -snapshot.createURL "http://victoriametrics:8428/snapshot/create" \
    -storageDataPath "/storage" \
    -dst "fs:///backup"

tar -czvf "/host/metrics.tar.gz" --strip-components=1 "/backup"