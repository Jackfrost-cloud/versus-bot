"""Génération des réponses lisibles (texte Discord) à partir des résultats du moteur."""
from __future__ import annotations

from .config import CAT_LABELS, STAT_CATEGORIES
from .text import chunk

CATS = [("force", "💪", "Force"), ("vitesse", "⚡", "Vitesse"), ("durabilite", "🛡️", "Durabilité"),
        ("puissance", "💥", "Puissance"), ("endurance", "🔋", "Endurance"), ("battle_iq", "🧠", "Battle IQ"),
        ("experience", "📚", "Expérience"), ("hax", "🌀", "Hax"), ("resistances", "🧱", "Résistances"),
        ("versatilite", "🎛️", "Versatilité"), ("matchup", "🎯", "Matchup")]
SEP = "━━━━━━━━━━━━━━━━"


def adv_text(a: float, b: float, na: str, nb: str) -> str:
    d = a - b
    if abs(d) < 2:
        return "égalité"
    lvl = "avantage léger" if abs(d) < 6 else "avantage" if abs(d) < 15 else "avantage important"
    return f"{na if d > 0 else nb} : {lvl}"


def pct(x: float) -> int:
    return round(100 * x)


def _reasons(res, ev, winner_is_a: bool):
    from .config import SPEC_WEIGHTS
    scored = []
    for key, (a, b) in ev.cats.items():
        d = (a - b) if winner_is_a else (b - a)
        scored.append((d * SPEC_WEIGHTS[key], key, d))
    scored.sort(reverse=True)
    names = {k: l for k, _, l in CATS}
    return [(names[k], d) for s, k, d in scored[:3] if d > 2]


def explain(res) -> list:
    W, L = (res.a, res.b) if res.p_a >= 0.5 else (res.b, res.a)
    ev = res.sim.main
    wa = res.p_a >= 0.5
    lines = []
    for i, (label, d) in enumerate(_reasons(res, ev, wa), 1):
        lines.append(f"{i}. Avantage en {label} (écart {d:.0f} pts sur 100)")
    wr = ev.routes_a if wa else ev.routes_b
    lr = ev.routes_b if wa else ev.routes_a
    if wr:
        lines.append(f"{len(lines) + 1}. Meilleure route de {W.short} : {wr[0].name} ({pct(wr[0].p)}%)"
                     + (f" — {wr[0].note}" if wr[0].note else ""))
    if lr:
        lines.append(f"{len(lines) + 1}. {L.short} garde une route : {lr[0].name} ({pct(lr[0].p)}%)"
                     + (f" — {lr[0].note}" if lr[0].note else ""))
    return lines


def format_versus(res, detailed: bool = False) -> list:
    a, b, ev = res.a, res.b, res.sim.main
    na, nb = a.short, b.short
    win = res.winner
    pa = res.p_a if res.p_a >= 0.5 else 1 - res.p_a
    out = [f"⚔️ **{a.label}** vs **{b.label}**",
           f"Mode : {res.cond.describe()}"]
    for p, d in ((a, res.a_default), (b, res.b_default)):
        if d and len(p.character.forms) > 1:
            out.append(f"ℹ️ Forme par défaut pour {p.short} : {p.form.name or p.form_id} "
                       f"(précise une forme dans la question pour en changer)")
    if res.sim.note:
        out.append(f"ℹ️ {res.sim.note}")
    close = abs(res.p_a - 0.5) < 0.06
    out += ["", f"🏆 **Vainqueur probable : {win.short if not close else 'indécis (≈ égalité)'}**",
            f"Confiance : {pct(res.confidence.value)}% ({res.confidence.label})", SEP]
    for key, emo, label in CATS:
        if key in ev.cats:
            x, y = ev.cats[key]
            extra = f"  ({x:.0f} / {y:.0f})" if detailed else ""
            out.append(f"{emo} {label} — {adv_text(x, y, na, nb)}{extra}")
        else:
            out.append(f"{emo} {label} — donnée insuffisante")
    out += [SEP, "🔥 **Conditions de victoire**"]
    for p, routes in ((a, ev.routes_a), (b, ev.routes_b)):
        out.append(f"**{p.short}** :")
        for r in routes[:3] if routes else []:
            out.append(f"- {r.name} ({pct(r.p)}%)" + (f" — {r.note}" if r.note else ""))
        if not routes:
            out.append("- aucune route identifiée (donnée insuffisante)")
    out += [SEP, "📊 **Estimation du moteur**",
            f"{na} : {pct(res.p_a)}%  |  {nb} : {pct(1 - res.p_a)}%"]
    if ev.stalemate:
        out.append("⚠️ Aucun des deux n'a de route de victoire fiable : stalemate probable.")
    if close:
        concl = "Match très serré : le moteur ne peut pas trancher avec certitude."
    else:
        r = _reasons(res, ev, res.p_a >= 0.5)
        why = " et ".join(l.lower() for l, _ in r[:2]) or "l'ensemble des données"
        lose = res.b if res.p_a >= 0.5 else res.a
        lr = (ev.routes_b if res.p_a >= 0.5 else ev.routes_a)
        keep = f", mais {lose.short} garde {lr[0].name} ({pct(lr[0].p)}%)" if lr else ""
        concl = f"{win.short} l'emporte surtout grâce à {why}{keep}."
    out += [f"Conclusion : {concl}",
            "Ces pourcentages sont le résultat d'un calcul sur les données disponibles, pas une vérité."]
    for p in (a, b):
        if p.character.data_status != "verified":
            out.append(f"⚠️ Données de {p.short} : brouillon (références au niveau arc, pas au chapitre).")
            break
    out += [f"ℹ️ {n}" for n in res.confidence.notes]
    text = "\n".join(out)
    msgs = chunk(text)
    if detailed:
        msgs += format_detailed(res)
    return msgs


def format_detailed(res) -> list:
    a, b, ev = res.a, res.b, res.sim.main
    s = ["📋 **ANALYSE DÉTAILLÉE**", "", "**Pourquoi " + res.winner.short + " est donné gagnant :**"]
    s += explain(res)
    s += ["", "**Scénarios simulés (déterministes) :**"]
    for r in res.sim.scenarios:
        s.append(f"- {r.desc} (poids {pct(r.weight)}%) : {a.short} {pct(r.p_a)}% / {b.short} {pct(1 - r.p_a)}%")
    s += ["", "**Statistiques (valeur /100, confiance) :**"]
    for c in STAT_CATEGORIES:
        sa, sb = a.stats.get(c), b.stats.get(c)
        fa = f"{sa.value:.0f} ({pct(sa.confidence)}%)" if sa else "?"
        fb = f"{sb.value:.0f} ({pct(sb.confidence)}%)" if sb else "?"
        s.append(f"- {CAT_LABELS[c]} : {a.short} {fa} | {b.short} {fb}")
    s.append("")
    for p in (a, b):
        s.append(f"**Feats retenus — {p.label}**")
        for c in STAT_CATEGORIES:
            sv = p.stats.get(c)
            if sv:
                f, w = sv.feats[0]
                s.append(f"- {CAT_LABELS[c]} {f.value:.0f} [{f.kind}] {f.description} — {f.source.label}")
        s.append("")
    for p, opp in ((a, b), (b, a)):
        s.append(f"**Capacités de {p.short} contre {opp.short}**")
        rr = [r for r in (ev.routes_a if p is a else ev.routes_b) if r.kind == "hax"]
        for r in rr:
            s.append(f"- {r.name} : efficacité {pct(r.p)}%" + (f" — {r.note}" if r.note else ""))
        if not rr:
            s.append("- aucune capacité offensive spéciale")
        if p.resist:
            s.append("- Résistances : " + ", ".join(
                f"{t} {pct(v)}%" + (f" ({p.resist_via[t][0]})" if p.resist_via[t][0] else "")
                for t, v in sorted(p.resist.items())))
        if p.vuln:
            s.append("- Faiblesses : " + ", ".join(f"{t} {pct(v)}%" for t, v in sorted(p.vuln.items())))
        s.append("")
    s.append("**Scaling connu :**")
    if res.relations:
        for cat, txt, c, hops, rels in res.relations:
            s.append(f"- [{cat}] {txt} (confiance {pct(c)}%, {hops} saut(s)) — {rels[0].description}")
    else:
        s.append("- aucune relation de scaling directe ou transitive entre ces deux fiches")
    deriv = [f for p in (a, b) for f in p.derived]
    if deriv:
        s.append(f"- {len(deriv)} feat(s) implicite(s) issus du scaling ont été ajoutés aux statistiques")
    s += ["", "**Incertitudes & hypothèses :**"]
    low = [f"{p.short}/{CAT_LABELS[c]} ({pct(v.confidence)}%)" for p in (a, b)
           for c, v in p.stats.items() if v.confidence < 0.4]
    s.append("- Stats peu sûres : " + (", ".join(low) if low else "aucune"))
    if ev.excluded:
        s.append("- Catégories exclues (donnée insuffisante) : " + ", ".join(ev.excluded))
    kinds: dict = {}
    for p in (a, b):
        for sv in p.stats.values():
            for f, _ in sv.feats:
                kinds[f.kind] = kinds.get(f.kind, 0) + 1
    s.append("- Types de preuves : " + ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))
    s += ["", "**Sources utilisées :**"]
    seen = []
    for p in (a, b):
        for sv in p.stats.values():
            for f, _ in sv.feats:
                lab = f.source.label()
                if lab not in seen:
                    seen.append(lab)
    s += [f"- {x}" for x in seen]
    return chunk("\n".join(s))


def format_analyze(p) -> list:
    s = [f"📊 **{p.label}** (univers : {p.character.universe})", ""]
    for c in STAT_CATEGORIES:
        sv = p.stats.get(c)
        s.append(f"- {CAT_LABELS[c]} : " + (f"{sv.value:.0f}/100 (confiance {round(100 * sv.confidence)}%)"
                                            if sv else "Information inconnue dans la base"))
    s.append(f"Formes disponibles : " + ", ".join(f"{f.id}" for f in p.character.forms.values()))
    return chunk("\n".join(s))


def format_feats(p) -> list:
    ch = p.character
    chain = dict(ch.form_chain(p.form_id))
    s = [f"📜 **Feats — {p.label}**"]
    for f in sorted(ch.feats, key=lambda f: (f.category, -f.value)):
        if f.form == "*" or f.form in chain:
            s.append(f"- [{CAT_LABELS[f.category]} {f.value:.0f}, {f.kind}, {round(100 * f.confidence)}%] "
                     f"{f.description} — {f.source.label()}")
    return chunk("\n".join(s))


def format_abilities(p) -> list:
    s = [f"🌀 **Capacités — {p.label}**"]
    for a in p.abilities:
        s.append(f"- **{a.name}** [{', '.join(a.tags)}] puissance {a.potency:.2f}, fiabilité {a.reliability:.2f}, "
                 f"effet : {a.win_type}{', hax' if a.hax else ''} — {a.description}")
    if p.resist:
        s.append("Résistances : " + ", ".join(f"{t} {round(100 * v)}%" for t, v in sorted(p.resist.items())))
    if p.vuln:
        s.append("Faiblesses : " + ", ".join(f"{t} {round(100 * v)}%" for t, v in sorted(p.vuln.items())))
    return chunk("\n".join(s))


def format_sources(ch, sources: list) -> list:
    s = [f"🔎 **Sources — {ch.name}** (statut des données : {ch.data_status})"]
    s += [f"- {x.label()}" for x in sources] or ["- aucune source enregistrée"]
    return chunk("\n".join(s))


def format_forms(ch) -> list:
    s = [f"🧬 **Formes — {ch.name}** (défaut : {ch.default_form})"]
    for f in ch.forms.values():
        s.append(f"- `{f.id}` : {f.name or 'forme de base'}" + (f" (hérite de {', '.join(f.inherits)})" if f.inherits else ""))
    return chunk("\n".join(s))


def format_compare(pa, pb) -> list:
    s = [f"📏 **{pa.label}** vs **{pb.label}** (sans verdict)"]
    for c in STAT_CATEGORIES:
        x, y = pa.stats.get(c), pb.stats.get(c)
        s.append(f"- {CAT_LABELS[c]} : {pa.short} {f'{x.value:.0f}' if x else '?'} | {pb.short} {f'{y.value:.0f}' if y else '?'}")
    return chunk("\n".join(s))


HELP = """**Bot de versus (sans IA)** — le moteur calcule à partir d'une base de données locale.
Envoie-moi en MP : `Naruto vs Luffy`, `Goku vs Saitama bloodlusted`, `Madara vs Aizen avec égalisation`, `Gojo vs Sukuna combat à mort`, `qui gagne entre X et Y ?`
Précise une forme dans le nom : `Naruto baryon vs Goku ultra instinct`.
Commandes : `!versus [detailed] A vs B`, `!analyze X`, `!feats X`, `!abilities X`, `!sources X`, `!compare X Y`, `!form X`, `!help`
Admin : `!admin validate | reload | list | add` (+ fichier JSON joint)
Si une donnée manque, le bot répond « Information inconnue dans la base » plutôt que d'inventer."""
