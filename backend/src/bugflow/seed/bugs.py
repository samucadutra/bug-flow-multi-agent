"""Packaged seed dataset: 20 realistic English bugs.

`intended_component` and `intended_severity` document the design intent of each bug. They are
never stored in the database and never asserted against LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bugflow.enums import BugStatus

SEED_WINDOW_START = datetime(2026, 6, 1, tzinfo=UTC)
SEED_WINDOW_END = datetime(2026, 8, 30, tzinfo=UTC)
SEED_STATUS = BugStatus.OPEN.value


@dataclass(frozen=True)
class SeedBug:
    title: str
    description: str
    reproduction_steps: str
    system_version: str
    environment: str
    reporting_team: str
    opened_at: datetime
    intended_component: str
    intended_severity: str


SEED_BUGS: tuple[SeedBug, ...] = (
    SeedBug(
        title="Checkout button does nothing on Safari 17",
        description='Clicking "Place order" on the checkout page shows no response and sends no network call. Customers on Safari 17 cannot complete purchases.',
        reproduction_steps='1. Add an item to the cart.\n2. Go to checkout in Safari 17.\n3. Click "Place order".',
        system_version="web 3.8.2",
        environment="production",
        reporting_team="support",
        opened_at=datetime(2026, 6, 1, 9, 15, tzinfo=UTC),
        intended_component="frontend",
        intended_severity="critical",
    ),
    SeedBug(
        title="Nightly sales report times out after index change",
        description="The nightly sales report query now takes over 10 minutes and the job is killed by the scheduler. Before the index change it finished in about 40 seconds.",
        reproduction_steps="1. Apply migration 0042 on staging.\n2. Run the nightly sales report job.\n3. Watch the job log until the timeout.",
        system_version="api 2.14.0",
        environment="staging",
        reporting_team="data",
        opened_at=datetime(2026, 6, 4, 13, 40, tzinfo=UTC),
        intended_component="database",
        intended_severity="major",
    ),
    SeedBug(
        title="API token visible in browser network logs",
        description="The access token appears in the query string of the export URL, so it is stored in browser history, proxy logs and the network tab.",
        reproduction_steps="1. Open the export page.\n2. Open the browser network tab.\n3. Start an export and inspect the request URL.",
        system_version="web 3.8.0",
        environment="production",
        reporting_team="security",
        opened_at=datetime(2026, 6, 8, 8, 5, tzinfo=UTC),
        intended_component="security",
        intended_severity="critical",
    ),
    SeedBug(
        title="Login redirect loop after password reset",
        description="After resetting a password through the emailed link, the user is redirected between /login and /account until the browser stops with a too-many-redirects error.",
        reproduction_steps="1. Request a password reset.\n2. Open the link from the email and set a new password.\n3. Observe the redirect loop.",
        system_version="api 2.14.1",
        environment="production",
        reporting_team="support",
        opened_at=datetime(2026, 6, 11, 15, 20, tzinfo=UTC),
        intended_component="backend",
        intended_severity="major",
    ),
    SeedBug(
        title="Dashboard chart legend overlaps the plot on narrow screens",
        description="On screens narrower than 900 px the legend of the weekly activity chart covers the right part of the plot, hiding the latest data points.",
        reproduction_steps="1. Open the dashboard.\n2. Resize the window to 800 px wide.\n3. Look at the weekly activity chart.",
        system_version="web 3.9.0",
        environment="production",
        reporting_team="support",
        opened_at=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
        intended_component="ui_ux",
        intended_severity="minor",
    ),
    SeedBug(
        title="Webhook deliveries to the payment provider are silently dropped",
        description="Some payment confirmation webhooks never reach our order service. The provider dashboard shows 200 responses, but the orders stay in pending.",
        reproduction_steps="1. Pay for an order with a test card.\n2. Wait five minutes.\n3. Check the order status and the provider webhook log.",
        system_version="api 2.15.0",
        environment="production",
        reporting_team="support",
        opened_at=datetime(2026, 6, 19, 11, 30, tzinfo=UTC),
        intended_component="integration",
        intended_severity="major",
    ),
    SeedBug(
        title="Order totals lose cents when the cart has more than 50 items",
        description="Orders with more than 50 line items are charged a total that differs by a few cents from the cart total because of rounding applied per batch.",
        reproduction_steps="1. Add 60 different items with prices ending in .99.\n2. Compare the cart total with the charged total.",
        system_version="api 2.15.0",
        environment="production",
        reporting_team="support",
        opened_at=datetime(2026, 6, 22, 14, 10, tzinfo=UTC),
        intended_component="backend",
        intended_severity="critical",
    ),
    SeedBug(
        title="Admin panel accepts expired session tokens",
        description="A session token that expired two hours ago is still accepted by the admin panel API, so a stolen token stays valid after the intended timeout.",
        reproduction_steps="1. Log in to the admin panel and copy the session token.\n2. Wait until the token expires.\n3. Call the admin users endpoint with the token.",
        system_version="api 2.15.2",
        environment="production",
        reporting_team="qa",
        opened_at=datetime(2026, 6, 26, 9, 45, tzinfo=UTC),
        intended_component="security",
        intended_severity="critical",
    ),
    SeedBug(
        title="Promotion banner shows the wrong end date",
        description="The spring promotion banner shows an end date one day earlier than the configured date for users in timezones behind UTC.",
        reproduction_steps="1. Configure a promotion ending on the 30th.\n2. Open the storefront with the browser set to UTC-5.\n3. Read the banner.",
        system_version="web 3.9.1",
        environment="production",
        reporting_team="product",
        opened_at=datetime(2026, 7, 1, 16, 0, tzinfo=UTC),
        intended_component="backend",
        intended_severity="major",
    ),
    SeedBug(
        title="Customer search is slow after the new full-text index",
        description="Searching customers by name takes more than 6 seconds on staging after the full-text index was added, and the database CPU stays high.",
        reproduction_steps="1. Load the staging dataset.\n2. Search for a common surname in the customer list.\n3. Measure the response time.",
        system_version="api 2.16.0-rc1",
        environment="staging",
        reporting_team="qa",
        opened_at=datetime(2026, 7, 4, 10, 25, tzinfo=UTC),
        intended_component="database",
        intended_severity="major",
    ),
    SeedBug(
        title="Profile form loses typed data when validation fails",
        description="When the profile form is submitted with an invalid phone number, all other fields are cleared and the user must type everything again.",
        reproduction_steps='1. Open the profile form.\n2. Fill every field and enter "abc" as the phone number.\n3. Submit the form.',
        system_version="web 3.10.0-rc1",
        environment="staging",
        reporting_team="qa",
        opened_at=datetime(2026, 7, 8, 13, 5, tzinfo=UTC),
        intended_component="frontend",
        intended_severity="major",
    ),
    SeedBug(
        title="Empty state text is cut off in the orders table",
        description="The message shown for an empty orders table is truncated after the first word and has no ellipsis, so it reads as a broken label.",
        reproduction_steps="1. Log in with an account that has no orders.\n2. Open the orders page.\n3. Read the empty state message.",
        system_version="web 3.10.0-rc1",
        environment="staging",
        reporting_team="product",
        opened_at=datetime(2026, 7, 12, 9, 30, tzinfo=UTC),
        intended_component="ui_ux",
        intended_severity="minor",
    ),
    SeedBug(
        title="Tooltip stays open after the pointer leaves the icon",
        description="The help tooltip on the settings page stays visible after moving the mouse away and only closes after clicking elsewhere.",
        reproduction_steps='1. Open the settings page.\n2. Hover the help icon next to "Retention".\n3. Move the pointer away.',
        system_version="web 3.10.0",
        environment="staging",
        reporting_team="frontend",
        opened_at=datetime(2026, 7, 16, 11, 50, tzinfo=UTC),
        intended_component="frontend",
        intended_severity="minor",
    ),
    SeedBug(
        title="Sync job ignores the retry limit of the shipping API",
        description="When the shipping API returns 429, the sync job retries immediately without backoff and ignores the configured limit, which causes a flood of requests.",
        reproduction_steps="1. Point the sync job to the mock shipping API configured to return 429.\n2. Start the sync job.\n3. Count the requests in the mock log.",
        system_version="worker 1.7.3",
        environment="development",
        reporting_team="frontend",
        opened_at=datetime(2026, 7, 20, 15, 35, tzinfo=UTC),
        intended_component="integration",
        intended_severity="minor",
    ),
    SeedBug(
        title="Migration 0057 drops an index that the report queries need",
        description="The local migration 0057 removes the composite index on orders (customer_id, created_at), and the monthly report falls back to a sequential scan.",
        reproduction_steps="1. Apply all migrations on a fresh local database.\n2. Run EXPLAIN on the monthly report query.",
        system_version="api 2.16.0",
        environment="development",
        reporting_team="backend",
        opened_at=datetime(2026, 7, 23, 8, 40, tzinfo=UTC),
        intended_component="database",
        intended_severity="major",
    ),
    SeedBug(
        title="Background export crashes on usernames with accents",
        description="The export worker raises a UnicodeEncodeError when a username contains accented characters and the export job is marked as failed.",
        reproduction_steps='1. Create a user named "Jose Garcia" with accents.\n2. Start a full export.\n3. Read the worker log.',
        system_version="worker 1.7.4",
        environment="development",
        reporting_team="backend",
        opened_at=datetime(2026, 7, 27, 12, 15, tzinfo=UTC),
        intended_component="backend",
        intended_severity="major",
    ),
    SeedBug(
        title="Local compose file does not wait for the database",
        description="The API container starts before the database accepts connections and exits, so developers must restart it manually after docker compose up.",
        reproduction_steps="1. Run docker compose up on a clean machine.\n2. Watch the API container exit with a connection error.",
        system_version="ops 0.9.0",
        environment="development",
        reporting_team="devops",
        opened_at=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        intended_component="devops",
        intended_severity="minor",
    ),
    SeedBug(
        title="Load balancer health check marks healthy nodes as down",
        description="The health check path times out under moderate load, and the load balancer removes healthy nodes from the pool during the nightly batch window.",
        reproduction_steps='1. Run the load test profile "batch".\n2. Watch the node states in the load balancer console.',
        system_version="ops 1.3.0",
        environment="testing",
        reporting_team="qa",
        opened_at=datetime(2026, 8, 10, 14, 45, tzinfo=UTC),
        intended_component="infrastructure",
        intended_severity="minor",
    ),
    SeedBug(
        title="Container memory limit too low for the indexing job",
        description="The indexing job is killed by the out-of-memory killer when it processes more than 5,000 documents because the container limit is 256 MB.",
        reproduction_steps="1. Start the indexing job in the test cluster with 6,000 documents.\n2. Watch the container restart count.",
        system_version="ops 1.3.1",
        environment="testing",
        reporting_team="qa",
        opened_at=datetime(2026, 8, 18, 10, 20, tzinfo=UTC),
        intended_component="infrastructure",
        intended_severity="major",
    ),
    SeedBug(
        title="Release pipeline publishes the build with the wrong version label",
        description="The release pipeline tags the container image with the previous version when two releases are started on the same day.",
        reproduction_steps="1. Trigger the release pipeline twice on the same day.\n2. Compare the image tag with the git tag.",
        system_version="ops 1.3.2",
        environment="testing",
        reporting_team="devops",
        opened_at=datetime(2026, 8, 29, 17, 5, tzinfo=UTC),
        intended_component="devops",
        intended_severity="minor",
    ),
)
