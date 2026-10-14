import json
import os
import urllib.request
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path


USERNAME = os.getenv("GITHUB_USER", "monicasenthil28")
TOKEN = os.environ["GITHUB_TOKEN"]

OUTPUT = Path("contrib-heatmap.svg")


QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      startedAt
      endedAt
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            weekday
          }
        }
      }
    }
  }
}
"""


def fetch_contributions():
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {"login": USERNAME},
        }
    ).encode()

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-contribution-generator",
        },
    )

    with urllib.request.urlopen(request) as response:
        result = json.loads(response.read())

    if "errors" in result:
        raise RuntimeError(result["errors"])

    user = result["data"]["user"]

    if not user:
        raise RuntimeError(f"GitHub user '{USERNAME}' was not found.")

    return user["contributionsCollection"]


def calculate_streaks(days):
    ordered = sorted(days, key=lambda item: item["date"])

    counts = {
        datetime.strptime(day["date"], "%Y-%m-%d").date(): day["contributionCount"]
        for day in ordered
    }

    today = date.today()

    # Current streak:
    # count from today; if today is empty, allow yesterday as the latest complete day.
    cursor = today

    if counts.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    current = 0

    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= timedelta(days=1)

    # Longest streak
    longest = 0
    running = 0

    for day in ordered:
        if day["contributionCount"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    return current, longest


def month_labels(weeks):
    labels = []
    previous_month = None

    for week_index, week in enumerate(weeks):
        if not week["contributionDays"]:
            continue

        first_date = datetime.strptime(
            week["contributionDays"][0]["date"],
            "%Y-%m-%d",
        )

        month = first_date.strftime("%b")

        if month != previous_month:
            labels.append((week_index, month))
            previous_month = month

    return labels


def build_svg(collection):
    calendar = collection["contributionCalendar"]
    weeks = calendar["weeks"]

    days = [
        day
        for week in weeks
        for day in week["contributionDays"]
    ]

    current_streak, longest_streak = calculate_streaks(days)

    best_day = max(
        days,
        key=lambda d: d["contributionCount"],
        default=None,
    )

    total = calendar["totalContributions"]

    started = datetime.fromisoformat(
        collection["startedAt"].replace("Z", "+00:00")
    ).date()

    ended = datetime.fromisoformat(
        collection["endedAt"].replace("Z", "+00:00")
    ).date()

    # Layout
    width = 1050
    height = 320

    left = 62
    top = 82

    cell = 14
    gap = 4
    step = cell + gap

    grid_width = len(weeks) * step

    # GitHub-like dark palette
    colors = {
        "NONE": "#161b22",
        "FIRST_QUARTILE": "#0e4429",
        "SECOND_QUARTILE": "#006d32",
        "THIRD_QUARTILE": "#26a641",
        "FOURTH_QUARTILE": "#39d353",
    }

    out = []

    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )

    # Background
    out.append(
        '<rect width="100%" height="100%" rx="16" fill="#0d1117"/>'
    )

    # Border
    out.append(
        '<rect x="1" y="1" width="1048" height="318" rx="16" '
        'fill="none" stroke="#1f6feb" stroke-width="1.5"/>'
    )

    # Terminal header separator
    out.append(
        '<line x1="0" y1="42" x2="1050" y2="42" '
        'stroke="#1f6feb" stroke-opacity=".65"/>'
    )

    # Terminal dots
    out.append('<circle cx="26" cy="21" r="6" fill="#ff5f56"/>')
    out.append('<circle cx="46" cy="21" r="6" fill="#ffbd2e"/>')
    out.append('<circle cx="66" cy="21" r="6" fill="#27c93f"/>')

    # Terminal title
    out.append(
        f'<text x="525" y="26" text-anchor="middle" '
        'fill="#8b949e" font-size="13" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        f'{escape(USERNAME)}@github: ~/contributions --graph'
        '</text>'
    )

    # Month labels
    for week_index, month in month_labels(weeks):
        x = left + week_index * step

        out.append(
            f'<text x="{x}" y="67" '
            'fill="#8b949e" font-size="11" '
            'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
            f'{month}'
            '</text>'
        )

    # Day labels
    labels = {
        1: "Mon",
        3: "Wed",
        5: "Fri",
    }

    for weekday, label in labels.items():
        y = top + weekday * step + 11

        out.append(
            f'<text x="25" y="{y}" '
            'fill="#8b949e" font-size="10" '
            'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
            f'{label}'
            '</text>'
        )

    # Contribution cells
    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            weekday = day["weekday"]

            x = left + week_index * step
            y = top + weekday * step

            level = day["contributionLevel"]
            color = colors.get(level, colors["NONE"])

            count = day["contributionCount"]
            day_date = day["date"]

            out.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                f'rx="2.5" fill="{color}">'
                f'<title>{count} contributions on {day_date}</title>'
                '</rect>'
            )

    # Legend
    legend_y = top + 7 * step + 17
    legend_x = left + grid_width - 165

    out.append(
        f'<text x="{legend_x}" y="{legend_y + 11}" '
        'fill="#8b949e" font-size="10" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        'Less'
        '</text>'
    )

    legend_colors = [
        "#161b22",
        "#0e4429",
        "#006d32",
        "#26a641",
        "#39d353",
    ]

    lx = legend_x + 42

    for color in legend_colors:
        out.append(
            f'<rect x="{lx}" y="{legend_y}" '
            f'width="13" height="13" rx="2" fill="{color}"/>'
        )

        lx += 17

    out.append(
        f'<text x="{lx + 4}" y="{legend_y + 11}" '
        'fill="#8b949e" font-size="10" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        'More'
        '</text>'
    )

    # Divider
    divider_y = 224

    out.append(
        f'<line x1="0" y1="{divider_y}" x2="1050" y2="{divider_y}" '
        'stroke="#1f6feb" stroke-opacity=".65"/>'
    )

    # Bottom-left contribution total
    out.append(
        '<text x="28" y="258" '
        'fill="#39d353" font-size="14" font-weight="bold" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        f'{total}'
        '</text>'
    )

    out.append(
        '<text x="65" y="258" '
        'fill="#8b949e" font-size="13" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        ' contributions in the last year'
        '</text>'
    )

    # Streak
    out.append(
        '<text x="28" y="290" '
        'fill="#8b949e" font-size="13" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        'current streak '
        f'<tspan fill="#00d9ff" font-weight="bold">{current_streak} days</tspan>'
        ' · longest '
        f'<tspan fill="#00d9ff" font-weight="bold">{longest_streak} days</tspan>'
        '</text>'
    )

    # Date range
    out.append(
        '<text x="1018" y="258" text-anchor="end" '
        'fill="#8b949e" font-size="12" '
        'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
        f'{started} → {ended}'
        '</text>'
    )

    # Best day
    if best_day:
        out.append(
            '<text x="1018" y="290" text-anchor="end" '
            'fill="#8b949e" font-size="12" '
            'font-family="ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">'
            'best day '
            f'<tspan fill="#f2cc60" font-weight="bold">'
            f'{best_day["contributionCount"]}'
            '</tspan>'
            f' on {best_day["date"]}'
            '</text>'
        )

    out.append("</svg>")

    return "\n".join(out)


def main():
    collection = fetch_contributions()

    svg = build_svg(collection)

    OUTPUT.write_text(svg, encoding="utf-8")

    print(f"Generated {OUTPUT}")
    print(f"GitHub user: {USERNAME}")
    print(
        "Total contributions:",
        collection["contributionCalendar"]["totalContributions"],
    )


if __name__ == "__main__":
    main()
