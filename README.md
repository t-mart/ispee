# conn-probe

![docs](docs/dashboard-demo.png)

conn-probe gives you an idea of the performance of your internet connection. By routinely "pinging"
hosts around the web, conn-probe visualizes:

- latency
- jitter
- packet loss/outages

Use this to get a quantitative idea about your connection's latency, so you can complain with
confidence to your ISP.

## Usage

1. Ensure you have [Docker Desktop](https://www.docker.com/products/docker-desktop)
   and [git](https://git-scm.com/downloads) on your system.
2. Clone this repository:

   ```shell
   git clone https://github.com/t-mart/conn-probe.git
   ```

3. Start the application:

   ```shell
   cd conn-probe/
   docker compose up --detach --build --always-recreate-deps
   ```

   Then, the following servers will be available:

   - Grafana: <http://localhost:3000>
     - **Dashboard: <http://localhost:3000/d/internet-performance/internet-performance>**
       (You probably want this one!!)
   - Prometheus: <http://localhost:9090>
   - Prober Server: <http://localhost:8000>

## Probes

conn-probe supports currently supports two types of probes (or "pings"):

- ICMP ping probes (`icmp-ping`) measure how long it takes for a host to reply to an ICMP request.
- TCP ping probes (`tcp-ping`) measure how long it takes for a host to reply to a `SYN` TCP packet
  on a particular port with a `SYN-ACK` response. These are the first two steps of the
  [TCP 3-step handshake](https://developer.mozilla.org/en-US/docs/Glossary/TCP_handshake).
  No data is otherwise transfered.

You should expect ICMP to be a little bit faster than TCP.

## Configuration

conn-probe requires a configuration file that defines how it runs. A default configuration is
given at [probes.yml](probes.yml) and this file will be automatically used in the Docker Compose
application.

The schema for `probes.yml` is demonstrated by this example:

```yaml
probes:
  - host: "1.2.3.4"
    type: icmp-ping
  - host: "google.com"
    type: tcp-ping
    port: 80
```

- `probes`: list, required
  - `probes` item: object, optional. Groups parameters related to a probe.
    - `host`: string, required. Specifies a host. Can be an IP or domain name.
    - `type`: string, required. May be either `icmp-ping` or `tcp-ping` for behavior as described
      above.
    - `port`: integer between 0 and 65,535, required if `type` == `tcp-ping`. Specifies the
      destination port on which to connect to `host`.

Validation of the configuration is minimal for now, and if you mess up, conn-probe may give you an
error message or may just barf.

### Default Configuration

The default configuration file is preloaded a set of DNS providers for both ICMP and TCP pings.

DNS providers are good for 2 reasons:

1. These hosts are designed to be addressed by IP, so we don't need to do a DNS resolution, which
would inflate the measurements potentially.
2. These services are designed for general public use. So, they, uhm, can handle this kind of
activity? We don't send much data, I promise.
3. They have a TCP port open that we know about, port 53, so we can `tcp-ping`.

(We're not actually doing DNS lookups with these hosts.)

## Development

### Grafana

The Grafana dashboard should be periodically exported with `make export-grafana` and
committed. Requires `httpie` and `jq`.
