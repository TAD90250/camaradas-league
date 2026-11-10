/* Weekly-prize tracker for the home page (Camaradas only).
   Reads data/live.json (written by export_site_data.py) and Sleeper's public API straight from the visitor's browser,
   so the numbers are live: no scheduled job is needed for the in-week updates. */
(function () {
  const API = "https://api.sleeper.app/v1";
  const TZ = "America/Los_Angeles";
  // Typical Pacific kickoff and finish times; a Thanksgiving or holiday slate will not match exactly.
  const DAY = 1440;                                    // minutes; the "game week" starts Wednesday 00:00
  const STAGES = [
    { key: "thu",  label: "Thursday night game",   short: "Thu night",   start: 1 * DAY + 17 * 60 + 15, end: 1 * DAY + 20 * 60 + 30 },
    { key: "sun1", label: "Sunday 10 AM games",    short: "Sun 10 AM",   start: 4 * DAY + 10 * 60,      end: 4 * DAY + 13 * 60 + 15 },
    { key: "sun2", label: "Sunday 1 PM games",     short: "Sun 1 PM",    start: 4 * DAY + 13 * 60,      end: 4 * DAY + 16 * 60 + 30 },
    { key: "sun3", label: "Sunday 5:15 PM game",   short: "Sun 5:15 PM", start: 4 * DAY + 17 * 60 + 15, end: 4 * DAY + 20 * 60 + 30 },
    { key: "mon",  label: "Monday night game",     short: "Mon night",   start: 5 * DAY + 17 * 60 + 15, end: 5 * DAY + 20 * 60 + 30 },
  ];

  const css = `
  .lv-head{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between;margin:0 0 10px}
  .lv-prize{font-weight:800;font-size:1.05rem}
  .lv-prize span{color:var(--gold)}
  .lv-steps{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;padding:0;list-style:none}
  .lv-steps li{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:.82rem;font-weight:600;color:var(--muted);background:var(--card)}
  .lv-steps li.done{color:var(--win);border-color:var(--win)}
  .lv-steps li.live{color:var(--ink);border-color:var(--gold);background:var(--gold-soft)}
  .lv-leader{padding:16px;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;border-color:var(--gold)}
  .lv-leader .t{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700;width:100%}
  .lv-leader .n{font-size:1.6rem;font-weight:800;line-height:1.1}
  .lv-leader .d{color:var(--muted)}
  .lv-leader.final{background:var(--gold-soft)}
  .lv-top{margin-top:12px}
  .lv-foot{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;color:var(--muted);font-size:.85rem;margin-top:8px}
  .lv-foot button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:3px 10px;cursor:pointer}
  `;

  const ptNow = () => {
    const f = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", hour: "numeric", minute: "numeric", hourCycle: "h23" });
    const o = {};
    f.formatToParts(new Date()).forEach((p) => { o[p.type] = p.value; });
    const dow = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[o.weekday];
    const m = (+o.hour % 24) * 60 + +o.minute;
    return { dow, m, t: ((dow - 3 + 7) % 7) * DAY + m };           // minutes since Wednesday 00:00 Pacific
  };
  const stageStates = (t, forceFinal) =>
    STAGES.map((s) => (forceFinal || t >= s.end ? "done" : t >= s.start ? "live" : "todo"));

  const num = (v, d) => Number(v).toLocaleString(undefined, { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d });

  async function api(path) {
    const r = await fetch(API + "/" + path, { cache: "no-store" });
    if (!r.ok) throw new Error("Sleeper " + r.status);
    return r.json();
  }

  // ---------------------------------------------------------------------------------------------- prize rules (live)
  function build(live, rows, prize, week) {
    const own = (rid) => live.rosterOwner[String(rid)];
    const teams = rows.filter((r) => own(r.roster_id)).map((r) => ({
      o: own(r.roster_id), mid: r.matchup_id, pts: +r.points || 0,
      starters: (r.starters || []).map((pid, i) => {
        const p = live.players[pid] || {};
        return { pid, name: p.n || pid, pos: p.p || "", pts: +((r.starters_points || [])[i]) || 0 };
      }),
    }));
    teams.forEach((t) => { t.best = Math.max(0, ...t.starters.map((s) => s.pts)); });
    const pairs = {};
    teams.forEach((t) => { if (t.mid != null) (pairs[t.mid] = pairs[t.mid] || []).push(t); });
    const games = Object.values(pairs).filter((g) => g.length === 2).map(([a, b]) => ({ a, b }));
    const anyPts = teams.some((t) => t.pts > 0);
    const rank = {};
    (live.standings || []).forEach((s) => { rank[s.slug] = s.rank; });
    const out = { list: [], head: "", empty: !anyPts };
    if (!anyPts) return out;

    const kind = prize.kind;
    if (kind === "highScore") {
      out.head = "Highest score";
      out.list = teams.slice().sort((x, y) => y.pts - x.pts || y.best - x.best)
        .map((t) => ({ o: t.o, main: num(t.pts) + " pts", sub: "best starter " + num(t.best, 1), val: t.pts }));
    } else if (kind === "topPos") {
      const pos = prize.pos || null;
      const want = (s) => (pos ? (pos === "DST" ? s.pos === "DST" || s.pos === "DEF" : s.pos === pos) : s.pos !== "" && s.pos !== "QB");
      out.head = pos ? "Highest-scoring starting " + pos : "Highest-scoring starter who is not a QB";
      out.list = [].concat(...teams.map((t) => t.starters.filter(want).map((s) => ({ o: t.o, s }))))
        .sort((x, y) => y.s.pts - x.s.pts)
        .map((e) => ({ o: e.o, main: num(e.s.pts, 1) + " pts", sub: e.s.name + " (" + (e.s.pos === "DEF" ? "DST" : e.s.pos) + ")", val: e.s.pts }));
    } else if (kind === "blowout") {
      out.head = "Biggest margin of victory";
      out.list = games.map((g) => { const w = g.a.pts >= g.b.pts ? g.a : g.b, l = w === g.a ? g.b : g.a;
        return { o: w.o, main: "+" + num(w.pts - l.pts) + "", sub: "over " + l.o.nick + " (" + num(w.pts, 1) + " – " + num(l.pts, 1) + ")", val: w.pts - l.pts }; })
        .sort((x, y) => y.val - x.val);
    } else if (kind === "beatsHighLoser") {
      out.head = "Beat the highest-scoring losing team";
      out.list = games.map((g) => { const w = g.a.pts >= g.b.pts ? g.a : g.b, l = w === g.a ? g.b : g.a;
        return { o: w.o, main: "beating " + l.o.nick, sub: "loser has " + num(l.pts, 1) + " (winner " + num(w.pts, 1) + ")", val: l.pts }; })
        .sort((x, y) => y.val - x.val);
    } else if (kind === "bestRankLoser") {
      out.head = "Beat the best-ranked losing team";
      out.list = games.map((g) => { const w = g.a.pts >= g.b.pts ? g.a : g.b, l = w === g.a ? g.b : g.a;
        const rk = rank[l.o.slug] || 99;
        return { o: w.o, main: "beating " + l.o.nick, sub: "#" + rk + " in the standings, " + num(l.pts, 1) + " – " + num(w.pts, 1), val: rk }; })
        .sort((x, y) => x.val - y.val);
    } else if (kind === "firstAfter") {
      out.head = "1st place in the standings";
      out.note = "Decided by the standings after week " + week + " is final. Standings through week " + (live.lastDone || 0) + " are on this page.";
      out.list = [];
    } else if (kind === "manual") {
      const m = (live.manual || []).find((x) => x.week === week && x.kind === prize.id);
      out.head = "Entered by the commissioner";
      const mo = m && Object.values(live.rosterOwner).find((x) => x.slug === String(m.winner).toLowerCase());
      out.note = m ? "Winner entered: " + (mo ? mo.nick : m.winner) + "." : "The commissioner enters the winner once the week is over.";
      out.list = [];
    } else {
      out.head = prize.label;
      out.note = "This prize is worked out once the week's games are final.";
      out.list = [];
    }
    out.list = out.list.filter((e, i, arr) => i < 5 || e.val === arr[0].val);
    return out;
  }

  // ---------------------------------------------------------------------------------------------- page
  async function init(L) {
    const { $, esc, ownerLink } = L;
    const sec = $("#prizewatch");
    let live;
    try { live = await L.getJSON("data/live.json"); } catch (e) { return; }              // not generated yet: section stays hidden
    if (!live || !live.rosterOwner || !Object.keys(live.rosterOwner).length) return;
    if (!document.getElementById("lv-css")) {
      const st = document.createElement("style"); st.id = "lv-css"; st.textContent = css; document.head.appendChild(st);
    }
    let timer = null;

    async function pickWeek() {
      let wk = live.weekHint;
      try { const s = await api("state/nfl"); if (+s.season === +live.season && s.week) wk = +s.week; } catch (e) { /* keep the hint */ }
      let rows = await api("league/" + live.leagueId + "/matchups/" + wk);
      let forceFinal = false;
      const empty = !rows.some((r) => +r.points > 0);
      const now = ptNow();
      if (empty && wk > 1 && (now.dow === 2 || now.dow === 3)) {                       // Tue/Wed: Sleeper has moved on, show the week that just ended
        rows = await api("league/" + live.leagueId + "/matchups/" + (wk - 1));
        wk -= 1; forceFinal = true;
      }
      return { wk, rows, forceFinal, now };
    }

    async function draw() {
      let data;
      try { data = await pickWeek(); }
      catch (e) {
        sec.hidden = false;
        $("#lvBody").innerHTML = "<p class='note'>Live scores from Sleeper are not available right now (" + esc(String(e.message || e)) + "). Try again in a minute.</p>";
        return;
      }
      const { wk, rows, forceFinal, now } = data;
      const prize = (live.prizes || []).find((p) => p.week === wk);
      sec.hidden = false;
      $("#lvTitle").textContent = "Week " + wk + " prize watch";
      if (!prize) {
        $("#lvBody").innerHTML = "<p class='note'>There is no weekly prize for week " + wk + ".</p>";
        return;
      }
      const t = forceFinal ? 99 * DAY : now.t;
      const states = stageStates(t, forceFinal);
      const done = states.lastIndexOf("done"), liveIdx = states.indexOf("live");
      const isFinal = forceFinal || states[states.length - 1] === "done";
      const res = build(live, rows, prize, wk);

      const steps = STAGES.map((s, i) => "<li class='" + states[i] + "'>" + (states[i] === "done" ? "✓ " : states[i] === "live" ? "● " : "") + esc(s.short) + "</li>").join("");
      const lead = res.list[0];
      let lbl;
      if (res.empty) lbl = "Nothing has been scored yet this week";
      else if (isFinal) lbl = "Winner after the Monday night game";
      else if (liveIdx >= 0) lbl = "Leading right now, " + STAGES[liveIdx].label.toLowerCase() + " in progress";
      else if (done >= 0) lbl = "Leading after the " + STAGES[done].label.toLowerCase();
      else lbl = "Leading so far";
      const tied = lead && lead.val != null && res.list.filter((e) => Math.abs(e.val - lead.val) < 1e-9).length > 1;

      let html = "<div class='lv-head'><div class='lv-prize'>" + esc(prize.label.replace(/^Week \d+:\s*/i, "").replace(/^./, (c) => c.toUpperCase())) + " <span>$" + prize.amount + "</span></div></div>" +
        "<ul class='lv-steps'>" + steps + "</ul>";
      if (res.empty) {
        html += "<div class='card lv-leader'><div class='t'>" + esc(lbl) + "</div><div class='d'>Check back once the games start. Kickoff is typically Thursday evening.</div></div>";
      } else if (lead) {
        html += "<div class='card lv-leader" + (isFinal ? " final" : "") + "'><div class='t'>" + esc(lbl) + "</div><div class='n'>" + (isFinal ? "🏆 " : "") + ownerLink(lead.o.slug, lead.o.nick) + "</div><div class='d'>" + esc(lead.main) + " · " + esc(lead.sub) + (tied ? " · tied, see the list" : "") + "</div></div>";
        if (res.list.length > 1) {
          html += "<div class='card table-wrap lv-top'><table><thead><tr><th>#</th><th class='l'>Owner</th><th class='l'>" + (isFinal ? "Final" : "Right now") + "</th><th class='l'>Details</th></tr></thead><tbody>" +
            res.list.map((e, i) => "<tr><td class='rank'>" + (i + 1) + "</td><td class='l'>" + ownerLink(e.o.slug, e.o.nick) + "</td><td class='l'>" + esc(e.main) + "</td><td class='l'>" + esc(e.sub) + "</td></tr>").join("") + "</tbody></table></div>";
        }
      } else if (res.note) {
        html += "<div class='card lv-leader'><div class='t'>" + esc(res.head) + "</div><div class='d'>" + esc(res.note) + "</div></div>";
      }
      if (prize.rule) html += "<p class='note' style='margin:8px 0 0'>" + esc(prize.rule) + "</p>";
      const stamp = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      html += "<div class='lv-foot'><span>Live from Sleeper · updated " + stamp + (liveIdx >= 0 ? " · refreshes every minute" : "") + "</span><button type='button' id='lvRefresh'>Refresh</button></div>";
      $("#lvBody").innerHTML = html;
      $("#lvRefresh").addEventListener("click", draw);
      clearTimeout(timer);
      if (liveIdx >= 0 && !isFinal) timer = setTimeout(draw, 60000);
    }
    draw();
  }

  window.LiveTracker = { init, build, stageStates, STAGES };
})();
