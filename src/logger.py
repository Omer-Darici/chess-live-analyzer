# -*- coding: utf-8 -*-
"""Post-game records: JSONL + PGN + Turkish explanations.

The point of the tool is the *reason*, not just the move, so every entry
carries a Turkish prose explanation of why the chosen move won and why each
alternative was rejected.
"""
import json
from datetime import datetime
from pathlib import Path

import chess
import chess.pgn

from . import config
from .board_detect import position_key

MOVE_WORDS = {
    chess.PAWN: "piyon", chess.KNIGHT: "at", chess.BISHOP: "fil",
    chess.ROOK: "kale", chess.QUEEN: "vezir", chess.KING: "şah",
}
SIDE_WORDS = {True: "Beyaz", False: "Siyah"}


def sq_name(sq):
    return chess.square_name(sq)


def fmt_cp(cp):
    """Centipawns -> '+0.35' / '-1.20' / 'mat'."""
    if cp is None:
        return "?"
    if abs(cp) >= 90000:
        return "mat"
    return f"{cp / 100.0:+.2f}"


def move_label(board, mv):
    """Turkish, human-readable description of a move."""
    piece = board.piece_at(mv.from_square)
    name = MOVE_WORDS.get(piece.piece_type, "taş") if piece else "taş"
    if board.is_kingside_castling(mv):
        return "0-0 (kısa rok)"
    if board.is_queenside_castling(mv):
        return "0-0-0 (uzun rok)"
    cap = "x" if board.is_capture(mv) else "-"
    extra = ""
    if mv.promotion:
        extra = "=" + MOVE_WORDS.get(mv.promotion, "?")
    label = f"{name} {sq_name(mv.from_square)}{cap}{sq_name(mv.to_square)}{extra}"
    if board.is_en_passant(mv):
        label += " (geçen alma)"
    if board.gives_check(mv):
        label += "+"
    return label


def tactical_notes(board, mv):
    """Short Turkish reasons this specific move is attractive."""
    notes = []
    piece = board.piece_at(mv.from_square)
    if board.is_kingside_castling(mv) or board.is_queenside_castling(mv):
        notes.append("rok ile şahı güvenceye alıyor ve kaleyi oyuna katıyor")
    if board.is_capture(mv):
        victim = board.piece_at(mv.to_square)
        if victim:
            notes.append(f"rakip {MOVE_WORDS.get(victim.piece_type, 'taşı')} alıyor")
        else:
            notes.append("rakip piyonunu alıyor (geçen alma)")
    if board.gives_check(mv):
        notes.append("şah çekiyor, rakibi cevap vermeye zorluyor")
    if mv.promotion:
        notes.append("piyon terfi ediyor")
    # Rescuing a piece that is attacked and not defended enough.
    if piece and not board.is_capture(mv):
        if board.is_attacked_by(not board.turn, mv.from_square):
            notes.append("tehdit altındaki taşı kurtarıyor")
    if piece and piece.piece_type == chess.PAWN:
        if board.is_attacked_by(not board.turn, mv.to_square):
            pass  # pawn pushes into contact are normal, not worth calling out
    return notes


def explain(board, lines, my_color="white"):
    """Turkish paragraph: why the best move, why the others lost."""
    if not lines:
        return "Motor bu süre içinde hamle üretmedi."
    best = lines[0]
    b_label = move_label(board, best["move"])
    b_cp = best["score_cp"]

    pov = b_cp if my_color == "white" else -b_cp
    verdict = (
        "konumu sizin açınızdan kazançlı" if pov > 0.6
        else "dengeli" if abs(pov) <= 0.6
        else "sizin açınızdan kayıp riskli"
    )

    parts = [f"En iyi hamle **{b_label}** — puan {fmt_cp(b_cp)} "
             f"({SIDE_WORDS[True]} tarafı için, {verdict})."]

    notes = tactical_notes(board, best["move"])
    if notes:
        parts.append("Neden bu hamle: " + ", ".join(notes) + ".")

    alts = [l for l in lines[1:] if l["move"] != best["move"]]
    if alts:
        why = []
        for a in alts:
            gap = b_cp - a["score_cp"]
            a_label = move_label(board, a["move"])
            head = f"`{a_label}` ({fmt_cp(a['score_cp'])}, {a['depth']}. derinlik)"
            if abs(a["score_cp"]) >= 90000 and gap >= 60000:
                why.append(f"{head} — rakibe karşı matı kaçırıyor")
            elif gap >= 60000:
                why.append(f"{head} — kendine mat veriyor")
            elif gap >= 250:
                why.append(f"{head} — belirgin şekilde daha zayıf ({gap / 100:.2f} puan kayıp)")
            elif gap >= 60:
                why.append(f"{head} — ölçülebilir ölçüde geride ({gap / 100:.2f} puan kayıp)")
            else:
                why.append(f"{head} — neredeyse eşdeğer ama en iyi değil "
                           f"({gap / 100:+.2f} puan fark)")
        parts.append("Neden diğerleri elendi: " + "; ".join(why) + ".")
    else:
        parts.append("Diğer adaylar bu sürede yeterince derin incelenmedi.")

    pv = best.get("pv") or []
    if len(pv) > 1:
        seq = []
        b = board.copy()
        for uci in pv[:6]:
            try:
                mv = chess.Move.from_uci(uci)
                seq.append(move_label(b, mv))
                b.push(mv)
            except Exception:
                break
        if seq:
            parts.append("Motorun planı: " + " → ".join(seq) + ".")
    return " ".join(parts)


class GameLogger:
    """Appends JSONL entries and exports PGN + Markdown under logs/."""

    def __init__(self, path=None):
        base = Path(path) if path else config.LOG_DIR / "game.jsonl"
        self.path = base
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._start = datetime.now()
        self._entries = []
        self._new()

    def _new(self):
        self._start = datetime.now()
        self._entries = []
        self._moves = []
        self._board = chess.Board()
        self._my_color = config.get("my_color", "white")

    def new_game(self, fen=None):
        self._new()
        if fen:
            self._board = chess.Board(fen)

    @property
    def move_count(self):
        return len(self._moves)

    def record(self, board_before, lines, my_color=None, snapshot=None):
        """Log one analysed position; returns the Turkish explanation."""
        if not lines:
            return ""
        my = my_color or self._my_color
        best = lines[0]["move"]
        reason = explain(board_before, lines, my)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "fen_before": board_before.fen(),
            "side_to_move": "white" if board_before.turn else "black",
            "move": best.uci(),
            "label": move_label(board_before, best),
            "reason": reason,
            "eval_cp": lines[0]["score_cp"],
            "depth": max((l["depth"] for l in lines), default=0),
            "candidates": [
                {"move": l["move"].uci(),
                 "label": move_label(board_before, l["move"]),
                 "eval_cp": l["score_cp"],
                 "depth": l["depth"]}
                for l in lines
            ],
            "pv": [mv.uci() for mv in (lines[0].get("pv") or [])][:8],
        }
        if snapshot:
            entry["snapshot"] = snapshot
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._entries.append(entry)
        self._absorb(board_before)
        return reason

    def _absorb(self, board):
        """Track the game from what was actually seen on screen.

        The played move is *discovered*, not assumed. Pushing the engine's
        recommended move — which is what this used to do — writes a PGN of
        moves nobody played and diverges from the game the moment a player
        chooses differently. Between two consecutive reads exactly one move
        happened, so searching the tracked position's legal moves for the one
        that reproduces the new board identifies what was really played.

        A position with no connecting legal move means frames were missed (or
        a frame slipped through); resync to what is on screen rather than
        append a move that never happened.
        """
        if self._board is None:
            self._board = board.copy()
            return
        if position_key(self._board) == position_key(board):
            return
        for mv in self._board.legal_moves:
            probe = self._board.copy()
            probe.push(mv)
            if position_key(probe) == position_key(board):
                self._moves.append(mv.uci())
                self._board = probe
                return
        self._board = board.copy()

    def save(self, result="*"):
        """Write ``.md`` (Turkish) and ``.pgn``; returns the Markdown path."""
        stamp = self._start.strftime("%Y%m%d-%H%M%S")
        md_path = self.path.parent / f"game-{stamp}.md"
        pgn_path = self.path.parent / f"game-{stamp}.pgn"

        lines_out = [
            "# Satranç Canlı Analiz Kaydı",
            "",
            f"- **Başlangıç:** {self._start:%Y-%m-%d %H:%M:%S}",
            f"- **Başlangıç FEN:** {chess.Board().fen()}",
            f"- **Sonuç:** {result}",
            f"- **Toplam analiz:** {len(self._entries)} hamle",
            "",
            "## Hamleler ve Açıklamaları",
            "",
        ]
        for i, e in enumerate(self._entries, 1):
            side = "Beyaz" if e["side_to_move"] == "white" else "Siyah"
            lines_out.append(f"### {i}. {side}: {e['label']}")
            lines_out.append("")
            lines_out.append(f"- Puan: `{fmt_cp(e['eval_cp'])}` · Derinlik: {e['depth']}")
            lines_out.append(f"- Açıklama: {e['reason']}")
            cands = [c for c in e["candidates"][1:4]]
            if cands:
                alt = ", ".join(f"`{c['label']}` ({fmt_cp(c['eval_cp'])})" for c in cands)
                lines_out.append(f"- Reddedilenler: {alt}")
            lines_out.append("")

        if self._moves:
            lines_out += ["## PGN", "", "```", self._pgn_text(result), "```", ""]
        md_path.write_text("\n".join(lines_out), encoding="utf-8")
        pgn_path.write_text(self._pgn_text(result), encoding="utf-8")
        return md_path

    def _pgn_text(self, result):
        game = chess.pgn.Game()
        game.headers["Event"] = "Canlı Analiz"
        game.headers["Site"] = "Chess Live Analyzer"
        game.headers["Date"] = self._start.strftime("%Y.%m.%d")
        game.headers["Round"] = "1"
        game.headers["Result"] = result
        node = game
        b = chess.Board()
        for uci in self._moves:
            mv = chess.Move.from_uci(uci)
            node = node.add_line([mv])
            try:
                b.push(mv)
            except Exception:
                break
        # Attach the Turkish reason to the move it belongs to.
        node = game
        for entry in self._entries:
            if node.variations:
                node = node.variations[0]
                node.comment = entry["reason"][:600]
            else:
                break
        return str(game)
