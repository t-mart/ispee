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

5. Head to the dashboard at <http://localhost:3000/>.

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

The Grafana dashboards should be periodically backed up. Here's the process:

1. Ensure the project's virtualenv is activated.
2. Run:

   ```bash
   make backup-dashboards
   ```

   (This saves all the dashboards in JSON format to `grafana/dashboards`)
3. Commit the changes to version control, and push them.

The value in doing this is that if the grafana volume is somehow deleted, the work put into the
dashboards will be restorable.
