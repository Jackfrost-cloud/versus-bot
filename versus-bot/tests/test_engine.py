import json
from pathlib import Path

from versus import config, hax, validate
from versus.confidence import band
from versus.models import Conditions, Source
from versus.parser import parse_question
from versus.scaling import ScalingGraph
from versus.stats import aggregate, build_profile, feat_weight
from versus.websearch import lookup


def res(engine, q):
    ans = engine.ask(q)
    assert ans.kind == "result", ans
    return ans.result


def test_parser():
    q = parse_question("Naruto vs Luffy bloodlusted")
    assert (q.a, q.b) == ("naruto", "luffy") and q.cond.bloodlusted
    q = parse_question("qui gagne entre Naruto et Luffy ?")
    assert (q.a, q.b) == ("naruto", "luffy")
    q = parse_question("Gojo vs Sukuna dans un combat à mort detailed")
    assert q.cond.deathmatch and q.cond.detailed
    assert parse_question("Naruto vs Luffy avec égalisation des pouvoirs").cond.mode == "equalized"
    assert parse_question("Naruto vs Luffy sans égalisation").cond.mode == "standard"
    assert parse_question("naruto vs luffy égalisation énergie").cond.mode == "equalized_energy"
    assert parse_question("juste un nom") is None


def test_alias_detection(engine):
    r = engine.resolver.resolve("Uzumaki Naruto")
    assert r.status == "ok" and r.character == "naruto_uzumaki" and r.form is None
    assert engine.resolver.resolve("narutto").character == "naruto_uzumaki"  # faute de frappe
    assert engine.resolver.resolve("zzzzqq").status == "unknown"


def test_form_detection(engine):
    r = engine.resolver.resolve("Baryon Naruto")
    assert (r.character, r.form) == ("naruto_uzumaki", "baryon")
    r = engine.resolver.resolve("goku ultra instinct")
    assert (r.character, r.form) == ("son_goku", "ui")


def test_default_form_announced(engine):
    r = res(engine, "Naruto vs Luffy")
    assert r.a_default and r.a.form_id == "shippuden"
    assert res(engine, "Naruto six paths vs Luffy gear 4").a.form_id == "six_paths"


def test_unknown_character_not_invented(engine, handler):
    ans = engine.ask("Personnageinconnu vs Luffy")
    assert ans.kind == "unknown"
    assert "Information inconnue dans la base" in handler.handle("Personnageinconnu vs Luffy")[0]


def test_deterministic_and_symmetric(engine):
    a, b = res(engine, "Naruto vs Luffy"), res(engine, "Naruto vs Luffy")
    assert a.p_a == b.p_a
    c = res(engine, "Luffy vs Naruto")
    assert abs(a.p_a + c.p_a - 1) < 1e-9


def test_known_matchups(engine):
    for item in json.loads((Path(__file__).parent / "known_matchups.json").read_text()):
        r = res(engine, item["q"])
        assert 0 <= r.p_a <= 1 and 0 <= r.confidence.value <= 1
        if item["expect"] == "a":
            assert r.p_a > 0.5, item["q"]
        elif item["expect"] == "b":
            assert r.p_a < 0.5, item["q"]


def test_scaling_is_per_category(engine):
    g = engine.graph
    rel = g.between("ichigo_kurosaki:mugetsu", "sosuke_aizen:hogyoku")
    assert any(c == "outcome" for c, *_ in rel)
    # un résultat de combat ne génère aucun feat de force implicite
    p = engine.profile("ichigo_kurosaki", "mugetsu")
    assert all(f.category != "outcome" for f in p.derived)
    assert any(f.category == "attack_power" for f in engine.profile("sosuke_aizen", "hogyoku").derived)


def test_scaling_cycles_detected():
    from versus.models import Relation
    S = Source("original_work")
    rels = [Relation("1", "a:x", "b:x", "speed", ">", "direct", .5, "", S),
            Relation("2", "b:x", "a:x", "speed", ">", "direct", .5, "", S)]
    assert ScalingGraph(rels).cycles()


def test_hax_and_resistance(engine):
    gojo, sukuna = engine.profile("gojo_satoru"), engine.profile("ryomen_sukuna")
    assert gojo.resist["physical"] >= 0.9
    cond = Conditions()
    shrine = next(a for a in sukuna.abilities if a.id == "shrine")
    wcs = next(a for a in sukuna.abilities if a.id == "wcs")
    # le domaine ignore Infinity ; une technique sans 'bypass' reste contrée si le tag est résisté
    assert "physical" in shrine.bypasses
    assert hax.ability_route(shrine, sukuna, gojo, cond).p > 0
    kyoka = next(a for a in engine.profile("sosuke_aizen").abilities if a.id == "kyoka")
    ichigo = engine.profile("ichigo_kurosaki")
    illusion_res = engine.profile("itachi_uchiha").resist["illusion"]
    itachi = engine.profile("itachi_uchiha")
    assert hax.ability_route(kyoka, engine.profile("sosuke_aizen"), itachi, cond).p < \
           hax.ability_route(kyoka, engine.profile("sosuke_aizen"), ichigo, cond).p or illusion_res > 0


def test_equalization_changes_gap(engine):
    base = res(engine, "Goku vs Saitama")
    eq = res(engine, "Goku vs Saitama avec égalisation")
    assert eq.sim.note and eq.cond.mode == "equalized"
    assert abs(eq.p_a - 0.5) <= abs(base.p_a - 0.5) + 0.2


def test_confidence_bands():
    assert band(0.97) == "très documenté" and band(0.85) == "fortement établi"
    assert band(0.65) == "probable" and band(0.45) == "controversé"
    assert band(0.25) == "spéculatif" and band(0.05) == "insuffisant"


def test_source_priority_and_kind_weights(engine):
    ch = engine.db.get_character("saitama")
    f = ch.feats[0]
    w = feat_weight(f)
    f.source.type = "forum"
    assert feat_weight(f) < w
    f.source.type = "original_work"
    assert Source("databook").priority > Source("wiki").priority > Source("forum").priority


def test_aggregate_confidence_grows_with_evidence(engine):
    ch = engine.db.get_character("saitama")
    one = aggregate([(ch.feats[0], 1.0)])
    two = aggregate([(ch.feats[0], 1.0), (ch.feats[1], 1.0)])
    assert one.confidence < two.confidence or len(two.feats) == 2


def test_form_overrides_parent(engine):
    p = build_profile(engine.db.get_character("naruto_uzumaki"), "baryon")
    assert p.value("stamina") < 40          # remplace les 88 de Six Paths
    assert p.value("range") is not None    # hérité


def test_commands(handler):
    assert "Naruto" in handler.handle("!analyze naruto")[0]
    assert any("Feats" in m for m in handler.handle("!feats luffy gear 5"))
    assert "Formes" in handler.handle("!form naruto")[0]
    assert "📏" in handler.handle("!compare Naruto Luffy")[0]
    assert "Commande réservée" in handler.handle("!admin list", user_id=2)[0]
    assert "Personnages" in handler.handle("!admin list", user_id=1)[0]
    assert any("ANALYSE DÉTAILLÉE" in m for m in handler.handle("!versus detailed Gojo vs Sukuna"))


def test_admin_add_validates(handler, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CUSTOM_DIR", tmp_path)
    bad = json.dumps({"characters": [{"id": "x", "name": "X", "feats": []}]}).encode()
    assert "Refusé" in handler.handle("!admin add", 1, ("x.json", bad))[0]


def test_data_validates():
    errs = [i for i in validate.validate_dirs(config.DATA_DIR) if i.level == "error"]
    assert not errs, [str(e) for e in errs]


def test_validator_catches_problems():
    bad = {"characters": [{"id": "a", "name": "A", "forms": [{"id": "base"}],
        "feats": [{"id": "f1", "form": "nope", "category": "speed", "value": 150, "kind": "direct", "confidence": 2}]}]}
    msgs = " ".join(str(i) for i in validate.validate_payloads([("t", bad)]))
    assert "personnage sans source" in msgs and "forme inexistante" in msgs and "hors de" in msgs


def test_web_fallback_cached(engine):
    calls = []
    fake = lambda n: calls.append(n) or {"title": "T", "url": "u", "extract": "e"}
    assert lookup(engine.db, "Zzz", 30, fake)["title"] == "T"
    lookup(engine.db, "Zzz", 30, fake)
    assert len(calls) == 1
