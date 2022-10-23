# ISPee

![docs](docs/demo.gif)

ISPee measures the performance of your home internet connection and visualizes it on a graphing
dashboard.

Use this to get a quantitative idea about your connection, so you can complain with
confidence to your ISP.

Note: This is designed for me. My connection. For example, I have a whole bit dedicated to scraping
the performance stats for my modem (Arris S33). You can turn that off in the config though.

## Quickstart

1. Ensure you have [Docker Desktop](https://www.docker.com/products/docker-desktop)
   and [git](https://git-scm.com/downloads) on your system.

2. Clone this repository:

   ```shell
   git clone https://github.com/t-mart/ispee.git
   cd ispee/
   ```

3. Copy the config template to the config location and edit it:

   ```shell
   cp config-TEMPLATE.yml config.yml
   vim config.yml  # edit away
   ```

4. Start the application:

   ```shell
   docker compose up --detach --build --always-recreate-deps
   ```

5. Head to the dashboard at <http://localhost:3000/d/internet-performance/internet-performance>
   *(and the modem dashboard at <http://localhost:3000/d/modem-info/modem-info>)*.

   The dashboard may initially show "No Data" because the first metrics are making their way to
   Grafana. Just wait and/or reload the page. "No Data" may continue to show for the Failure graphs,
   which is a good thing because you haven't experienced any yet!

## Measurements

- ICMP ping duration
- UDP and TCP DNS lookup "ping" duration
- Own IP address
- Arris S33 Modem stuff

## Development

### Grafana

The Grafana dashboards should be periodically exported with `make export-grafana` and
committed. Requires `curl` and `jq`.

If a new dashboard is made, here's how to set it up for exporting:

1. Click the share icon. Export tab. View JSON.
2. Copy that JSON to `grafana/dashboards/<name>.json`.
3. In that file, find the `uid` field. Change it to something more memorable (versus the random
   characters that it gets by default). Ensure it's unique.
4. In the `Makefile`, under the `export-grafana` target, add another curl export line like the
   others have.
