#!/usr/bin/env python3
"""
Interface Visual TUI (ANSI 24-bit TrueColor Dashboard) do Console do Operador SunTzu.
Inclui:
- Tabuleiro colorido de alta legibilidade (casas claras/escuras, destaque de último lance,
  peças Unicode + letra em Português, orientação automática para Brancas ou Pretas).
- Barra vertical de avaliação (centipeões + expectativa 3-1-0).
- Retrato colorido em ANSI/ASCII Art do General Sun Tzu com pergaminho "孫子兵法" (Arte da Guerra).
- Balão de fala dinâmico onde Sun Tzu comenta a partida em tempo real conforme o estado tático
  (Livro 3-1-0, Pressão, Virada/Swindle, Conversão, Ponderhit, Xeque, Captura, Pânico de Tempo,
  Repetição Tripla/50 lances).
- Painel lateral fixo de telemetria ("Doutrina Arte da Guerra", Relógios Físicos, Histórico PGN
  e Banner de Execução no Tabuleiro Físico).
"""

import os
import re
import shutil
from typing import Dict, List, Optional, Tuple

import chess

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def vis_len(text: str) -> int:
    return len(strip_ansi(text))


def pad_ansi(text: str, width: int) -> str:
    diff = width - vis_len(text)
    if diff > 0:
        return text + (" " * diff)
    return text


def fg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def bg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

# Paleta temática Imperial SunTzu
GOLD = fg_rgb(245, 197, 66)
BRIGHT_GOLD = fg_rgb(255, 223, 100)
CRIMSON = fg_rgb(220, 60, 55)
JADE = fg_rgb(72, 209, 142)
CYAN = fg_rgb(95, 205, 228)
SILVER = fg_rgb(200, 205, 215)
MUTED = fg_rgb(135, 142, 155)
WHITE_FG = fg_rgb(250, 250, 252)
ALERT_BG = bg_rgb(165, 28, 28) + WHITE_FG + BOLD
BANNER_BG = bg_rgb(22, 68, 45) + fg_rgb(230, 255, 235) + BOLD
CONFIRM_BG = bg_rgb(115, 78, 12) + BRIGHT_GOLD + BOLD

# Cores das casas do tabuleiro
BG_LIGHT_SQ = bg_rgb(218, 192, 150)
BG_DARK_SQ = bg_rgb(138, 98, 64)
BG_HIGHLIGHT_LIGHT = bg_rgb(235, 220, 105)
BG_HIGHLIGHT_DARK = bg_rgb(188, 168, 56)
BG_PENDING_SQ = bg_rgb(80, 165, 215)
BG_CHECK_SQ = bg_rgb(195, 55, 55)

FG_WHITE_PIECE = fg_rgb(255, 255, 255) + BOLD
FG_BLACK_PIECE = fg_rgb(20, 20, 25) + BOLD

UNICODE_PIECES = {
    (chess.PAWN, chess.WHITE): "♙",
    (chess.KNIGHT, chess.WHITE): "♘",
    (chess.BISHOP, chess.WHITE): "♗",
    (chess.ROOK, chess.WHITE): "♖",
    (chess.QUEEN, chess.WHITE): "♕",
    (chess.KING, chess.WHITE): "♔",
    (chess.PAWN, chess.BLACK): "♟",
    (chess.KNIGHT, chess.BLACK): "♞",
    (chess.BISHOP, chess.BLACK): "♝",
    (chess.ROOK, chess.BLACK): "♜",
    (chess.QUEEN, chess.BLACK): "♛",
    (chess.KING, chess.BLACK): "♚",
}

PT_LETTER = {
    chess.PAWN: "P",
    chess.KNIGHT: "C",
    chess.BISHOP: "B",
    chess.ROOK: "T",
    chess.QUEEN: "D",
    chess.KING: "R",
}


# ---------------------------------------------------------------------------
# Retrato do General Sun Tzu + Frases Contextuais ("A Arte da Guerra")
# ---------------------------------------------------------------------------

SUNTZU_WIKI_22X22 = [
    "\x1b[38;2;244;214;186;48;2;245;216;188m▀\x1b[38;2;243;213;185;48;2;244;214;186m▀\x1b[38;2;243;213;185;48;2;247;217;189m▀\x1b[38;2;246;216;188;48;2;245;217;189m▀\x1b[38;2;242;214;184;48;2;251;221;190m▀\x1b[38;2;244;214;178;48;2;235;207;177m▀\x1b[38;2;239;210;175;48;2;166;164;152m▀\x1b[38;2;232;207;177;48;2;153;154;149m▀\x1b[38;2;211;189;161;48;2;160;160;154m▀\x1b[38;2;192;176;158;48;2;184;183;177m▀\x1b[38;2;199;181;156;48;2;177;175;168m▀\x1b[38;2;207;183;157;48;2;167;167;157m▀\x1b[38;2;218;196;166;48;2;164;165;158m▀\x1b[38;2;239;212;177;48;2;223;203;177m▀\x1b[38;2;235;209;176;48;2;248;221;186m▀\x1b[38;2;236;211;176;48;2;243;216;184m▀\x1b[38;2;239;216;182;48;2;247;223;191m▀\x1b[38;2;241;217;185;48;2;248;223;194m▀\x1b[38;2;241;215;186;48;2;249;223;195m▀\x1b[38;2;244;221;191;48;2;249;223;194m▀\x1b[38;2;244;220;189;48;2;246;218;187m▀\x1b[38;2;245;219;188;48;2;244;216;182m▀\x1b[0m",
    "\x1b[38;2;247;218;190;48;2;247;217;187m▀\x1b[38;2;246;215;188;48;2;243;214;186m▀\x1b[38;2;246;216;188;48;2;247;217;188m▀\x1b[38;2;250;221;191;48;2;234;210;182m▀\x1b[38;2;230;206;174;48;2;143;152;154m▀\x1b[38;2;146;147;145;48;2;170;175;173m▀\x1b[38;2;151;158;157;48;2;179;180;174m▀\x1b[38;2;187;186;179;48;2;99;102;99m▀\x1b[38;2;150;153;153;48;2;59;51;45m▀\x1b[38;2;142;149;148;48;2;143;123;101m▀\x1b[38;2;147;149;147;48;2;180;154;129m▀\x1b[38;2;127;130;127;48;2;194;165;140m▀\x1b[38;2;112;117;118;48;2;204;173;143m▀\x1b[38;2;189;175;157;48;2;161;136;112m▀\x1b[38;2;255;230;198;48;2;200;184;157m▀\x1b[38;2;243;214;182;48;2;250;223;189m▀\x1b[38;2;246;222;191;48;2;243;218;189m▀\x1b[38;2;249;223;194;48;2;246;221;191m▀\x1b[38;2;248;223;194;48;2;245;220;190m▀\x1b[38;2;245;220;189;48;2;245;221;187m▀\x1b[38;2;245;216;185;48;2;244;217;184m▀\x1b[38;2;245;215;184;48;2;243;213;185m▀\x1b[0m",
    "\x1b[38;2;248;218;185;48;2;247;218;188m▀\x1b[38;2;247;221;192;48;2;250;224;194m▀\x1b[38;2;247;221;193;48;2;245;222;192m▀\x1b[38;2;238;215;189;48;2;255;229;199m▀\x1b[38;2;162;162;163;48;2;218;199;178m▀\x1b[38;2;146;156;160;48;2;118;130;139m▀\x1b[38;2;70;75;80;48;2;50;50;50m▀\x1b[38;2;70;56;47;48;2;177;143;109m▀\x1b[38;2;212;170;131;48;2;238;193;143m▀\x1b[38;2;243;203;160;48;2;241;201;158m▀\x1b[38;2;245;210;172;48;2;243;208;173m▀\x1b[38;2;246;210;177;48;2;242;207;175m▀\x1b[38;2;246;213;176;48;2;235;200;168m▀\x1b[38;2;240;202;165;48;2;242;208;172m▀\x1b[38;2;195;166;130;48;2;229;192;148m▀\x1b[38;2;251;227;194;48;2;217;195;163m▀\x1b[38;2;247;221;192;48;2;253;229;195m▀\x1b[38;2;244;220;187;48;2;247;223;189m▀\x1b[38;2;246;222;189;48;2;251;226;196m▀\x1b[38;2;246;221;191;48;2;250;225;197m▀\x1b[38;2;246;216;185;48;2;248;221;194m▀\x1b[38;2;244;214;185;48;2;246;219;189m▀\x1b[0m",
    "\x1b[38;2;248;220;190;48;2;248;223;193m▀\x1b[38;2;248;221;192;48;2;249;225;195m▀\x1b[38;2;247;219;189;48;2;247;221;193m▀\x1b[38;2;253;226;194;48;2;255;231;202m▀\x1b[38;2;210;195;179;48;2;217;203;190m▀\x1b[38;2;155;161;166;48;2;95;103;106m▀\x1b[38;2;72;69;65;48;2;18;17;19m▀\x1b[38;2;185;150;111;48;2;190;154;121m▀\x1b[38;2;199;162;129;48;2;215;178;143m▀\x1b[38;2;165;138;110;48;2;179;150;129m▀\x1b[38;2;220;187;154;48;2;195;161;127m▀\x1b[38;2;239;206;168;48;2;213;177;136m▀\x1b[38;2;234;201;165;48;2;234;199;164m▀\x1b[38;2;241;206;169;48;2;227;188;148m▀\x1b[38;2;205;169;133;48;2;203;171;133m▀\x1b[38;2;204;181;150;48;2;232;207;179m▀\x1b[38;2;255;234;198;48;2;254;230;199m▀\x1b[38;2;251;228;196;48;2;251;230;199m▀\x1b[38;2;252;232;206;48;2;250;231;202m▀\x1b[38;2;251;228;202;48;2;249;226;196m▀\x1b[38;2;249;224;194;48;2;249;224;193m▀\x1b[38;2;245;218;186;48;2;249;224;193m▀\x1b[0m",
    "\x1b[38;2;251;225;196;48;2;249;219;191m▀\x1b[38;2;250;226;194;48;2;249;220;191m▀\x1b[38;2;253;227;199;48;2;253;223;191m▀\x1b[38;2;234;210;185;48;2;216;190;162m▀\x1b[38;2;163;163;161;48;2;158;153;145m▀\x1b[38;2;137;124;111;48;2;228;197;162m▀\x1b[38;2;95;74;63;48;2;221;184;149m▀\x1b[38;2;173;137;107;48;2;198;163;125m▀\x1b[38;2;236;192;152;48;2;221;182;136m▀\x1b[38;2;235;200;166;48;2;228;190;146m▀\x1b[38;2;200;171;140;48;2;224;185;139m▀\x1b[38;2;205;171;138;48;2;230;190;151m▀\x1b[38;2;236;198;159;48;2;234;199;162m▀\x1b[38;2;220;180;140;48;2;234;194;155m▀\x1b[38;2;205;175;141;48;2;237;197;154m▀\x1b[38;2;226;198;163;48;2;230;194;151m▀\x1b[38;2;252;227;197;48;2;245;220;187m▀\x1b[38;2;249;225;194;48;2;248;224;192m▀\x1b[38;2;252;227;197;48;2;251;226;199m▀\x1b[38;2;250;225;195;48;2;252;229;201m▀\x1b[38;2;251;227;197;48;2;249;225;191m▀\x1b[38;2;251;227;196;48;2;250;224;192m▀\x1b[0m",
    "\x1b[38;2;251;225;196;48;2;253;228;199m▀\x1b[38;2;251;226;197;48;2;253;228;202m▀\x1b[38;2;255;226;193;48;2;255;233;202m▀\x1b[38;2;214;197;170;48;2;207;191;171m▀\x1b[38;2;198;187;170;48;2;236;215;189m▀\x1b[38;2;241;209;177;48;2;202;181;153m▀\x1b[38;2;219;186;154;48;2;83;74;64m▀\x1b[38;2;217;181;142;48;2;224;190;154m▀\x1b[38;2;223;183;134;48;2;223;187;144m▀\x1b[38;2;226;185;143;48;2;229;189;150m▀\x1b[38;2;227;184;140;48;2;227;184;144m▀\x1b[38;2;232;192;153;48;2;238;201;165m▀\x1b[38;2;233;196;157;48;2;124;110;89m▀\x1b[38;2;225;192;154;48;2;142;111;75m▀\x1b[38;2;219;185;145;48;2;148;115;82m▀\x1b[38;2;236;196;153;48;2;187;161;134m▀\x1b[38;2;240;216;182;48;2;252;227;192m▀\x1b[38;2;254;230;200;48;2;251;228;200m▀\x1b[38;2;249;231;199;48;2;249;229;197m▀\x1b[38;2;249;234;205;48;2;250;230;198m▀\x1b[38;2;248;229;198;48;2;251;230;201m▀\x1b[38;2;250;227;196;48;2;248;228;200m▀\x1b[0m",
    "\x1b[38;2;251;225;195;48;2;250;226;196m▀\x1b[38;2;253;228;201;48;2;254;231;202m▀\x1b[38;2;254;229;200;48;2;250;226;196m▀\x1b[38;2;239;212;183;48;2;244;214;182m▀\x1b[38;2;248;216;181;48;2;253;222;185m▀\x1b[38;2;217;197;174;48;2;196;177;154m▀\x1b[38;2;102;91;93;48;2;205;192;185m▀\x1b[38;2;196;165;131;48;2;231;195;160m▀\x1b[38;2;228;194;154;48;2;221;180;141m▀\x1b[38;2;238;201;166;48;2;239;201;162m▀\x1b[38;2;249;209;176;48;2;239;204;170m▀\x1b[38;2;190;163;138;48;2;163;140;119m▀\x1b[38;2;118;104;85;48;2;244;211;169m▀\x1b[38;2;218;175;131;48;2;234;202;163m▀\x1b[38;2;202;163;124;48;2;169;145;120m▀\x1b[38;2;178;152;126;48;2;207;185;156m▀\x1b[38;2;240;222;192;48;2;250;233;203m▀\x1b[38;2;252;230;196;48;2;253;233;202m▀\x1b[38;2;250;224;194;48;2;249;229;200m▀\x1b[38;2;250;226;194;48;2;251;230;200m▀\x1b[38;2;249;226;197;48;2;249;231;202m▀\x1b[38;2;249;227;199;48;2;250;234;208m▀\x1b[0m",
    "\x1b[38;2;252;229;200;48;2;250;228;197m▀\x1b[38;2;253;230;203;48;2;255;233;205m▀\x1b[38;2;251;225;198;48;2;251;227;197m▀\x1b[38;2;252;221;191;48;2;220;196;167m▀\x1b[38;2;249;221;186;48;2;197;177;159m▀\x1b[38;2;96;88;72;48;2;47;46;45m▀\x1b[38;2;133;128;126;48;2;59;60;57m▀\x1b[38;2;235;210;186;48;2;229;223;223m▀\x1b[38;2;219;182;144;48;2;232;217;206m▀\x1b[38;2;226;186;143;48;2;221;190;160m▀\x1b[38;2;211;176;138;48;2;226;189;156m▀\x1b[38;2;226;192;159;48;2;223;187;156m▀\x1b[38;2;224;194;159;48;2;216;186;153m▀\x1b[38;2;92;80;64;48;2;68;54;46m▀\x1b[38;2;31;27;24;48;2;0;0;0m▀\x1b[38;2;140;131;117;48;2;91;82;76m▀\x1b[38;2;240;224;197;48;2;209;192;175m▀\x1b[38;2;249;232;202;48;2;201;183;163m▀\x1b[38;2;255;238;207;48;2;216;200;173m▀\x1b[38;2;251;234;206;48;2;244;228;197m▀\x1b[38;2;249;232;206;48;2;251;234;205m▀\x1b[38;2;251;233;206;48;2;247;229;200m▀\x1b[0m",
    "\x1b[38;2;255;238;210;48;2;216;202;178m▀\x1b[38;2;236;219;188;48;2;203;187;175m▀\x1b[38;2;199;180;158;48;2;224;205;191m▀\x1b[38;2;200;181;172;48;2;227;208;195m▀\x1b[38;2;241;220;210;48;2;235;216;205m▀\x1b[38;2;84;76;74;48;2;157;143;135m▀\x1b[38;2;4;4;11;48;2;0;0;6m▀\x1b[38;2;99;93;88;48;2;20;22;25m▀\x1b[38;2;243;240;236;48;2;96;91;82m▀\x1b[38;2;237;223;219;48;2;233;228;228m▀\x1b[38;2;221;189;158;48;2;218;202;192m▀\x1b[38;2;234;201;170;48;2;213;181;150m▀\x1b[38;2;238;205;171;48;2;231;209;182m▀\x1b[38;2;180;157;136;48;2;215;204;195m▀\x1b[38;2;32;24;26;48;2;84;74;63m▀\x1b[38;2;46;44;42;48;2;44;42;40m▀\x1b[38;2;214;201;188;48;2;190;177;169m▀\x1b[38;2;232;212;198;48;2;219;204;197m▀\x1b[38;2;209;192;180;48;2;238;218;207m▀\x1b[38;2;199;180;165;48;2;233;212;202m▀\x1b[38;2;222;204;176;48;2;204;184;168m▀\x1b[38;2;250;231;201;48;2;206;190;167m▀\x1b[0m",
    "\x1b[38;2;214;198;187;48;2;235;216;205m▀\x1b[38;2;239;221;207;48;2;221;204;192m▀\x1b[38;2;193;181;174;48;2;183;176;176m▀\x1b[38;2;220;202;195;48;2;230;210;199m▀\x1b[38;2;226;207;198;48;2;224;204;194m▀\x1b[38;2;228;209;196;48;2;232;212;200m▀\x1b[38;2;53;48;49;48;2;183;164;155m▀\x1b[38;2;0;0;7;48;2;2;0;3m▀\x1b[38;2;21;20;24;48;2;1;4;8m▀\x1b[38;2;68;64;62;48;2;15;16;20m▀\x1b[38;2;170;159;157;48;2;33;29;28m▀\x1b[38;2;229;218;218;48;2;107;104;101m▀\x1b[38;2;237;229;227;48;2;127;118;111m▀\x1b[38;2;99;92;83;48;2;40;37;33m▀\x1b[38;2;22;21;21;48;2;0;0;0m▀\x1b[38;2;47;44;43;48;2;79;76;73m▀\x1b[38;2;209;194;179;48;2;234;218;208m▀\x1b[38;2;197;186;182;48;2;203;187;178m▀\x1b[38;2;222;205;194;48;2;196;183;179m▀\x1b[38;2;232;211;199;48;2;235;214;200m▀\x1b[38;2;234;216;201;48;2;219;198;185m▀\x1b[38;2;210;192;178;48;2;209;195;185m▀\x1b[0m",
    "\x1b[38;2;230;210;199;48;2;231;211;200m▀\x1b[38;2;208;193;189;48;2;197;183;181m▀\x1b[38;2;189;180;180;48;2;192;183;182m▀\x1b[38;2;229;210;198;48;2;228;208;198m▀\x1b[38;2;222;203;191;48;2;222;203;191m▀\x1b[38;2;217;197;186;48;2;221;201;191m▀\x1b[38;2;237;217;203;48;2;218;200;192m▀\x1b[38;2;142;127;120;48;2;240;220;208m▀\x1b[38;2;0;0;0;48;2;117;103;98m▀\x1b[38;2;3;5;8;48;2;0;0;0m▀\x1b[38;2;9;12;18;48;2;29;26;25m▀\x1b[38;2;41;39;36;48;2;54;53;47m▀\x1b[38;2;44;42;35;48;2;21;22;26m▀\x1b[38;2;9;9;11;48;2;0;0;0m▀\x1b[38;2;6;8;12;48;2;94;87;83m▀\x1b[38;2;183;170;162;48;2;232;213;204m▀\x1b[38;2;231;211;205;48;2;218;200;190m▀\x1b[38;2;222;204;193;48;2;227;209;196m▀\x1b[38;2;189;175;169;48;2;201;186;174m▀\x1b[38;2;223;204;190;48;2;203;188;178m▀\x1b[38;2;221;202;188;48;2;228;208;193m▀\x1b[38;2;174;165;162;48;2;190;178;169m▀\x1b[0m",
]


_KITTY_PNG_CHUNKS: Optional[List[str]] = None


def _get_kitty_png_escape(row: int, col: int, cols_w: int = 22, rows_h: int = 11) -> str:
    global _KITTY_PNG_CHUNKS
    term = os.environ.get("TERM", "").lower()
    supports_kitty = (
        "ghostty" in term
        or "kitty" in term
        or "wezterm" in term
        or "GHOSTTY_RESOURCES_DIR" in os.environ
        or os.environ.get("SUNTZU_KITTY_IMG") == "1"
    )
    if not supports_kitty:
        return ""

    if _KITTY_PNG_CHUNKS is None:
        import base64
        png_path = os.path.join(os.path.dirname(__file__), "assets", "suntzu_wiki_portrait.png")
        if not os.path.isfile(png_path):
            _KITTY_PNG_CHUNKS = []
            return ""
        with open(png_path, "rb") as fp:
            b64 = base64.b64encode(fp.read()).decode("ascii")
        _KITTY_PNG_CHUNKS = [b64[i : i + 4096] for i in range(0, len(b64), 4096)]

    if not _KITTY_PNG_CHUNKS:
        return ""

    seq = [f"\x1b7\x1b[{row};{col}H\x1b_Ga=d,d=i,i=77,q=2\x1b\\"]
    for idx, chunk in enumerate(_KITTY_PNG_CHUNKS):
        more = 1 if idx < len(_KITTY_PNG_CHUNKS) - 1 else 0
        if idx == 0:
            seq.append(f"\x1b_Ga=T,f=100,i=77,q=2,c={cols_w},r={rows_h},C=1,m={more};{chunk}\x1b\\")
        else:
            seq.append(f"\x1b_Gm={more},q=2;{chunk}\x1b\\")
    seq.append("\x1b8")
    return "".join(seq)


def get_suntzu_portrait_lines(mood: str = "normal") -> List[str]:
    """
    Retorna as 11 linhas (22 colunas) da pintura histórica real de Sun Tzu (Wikipedia: 吴司马孙武.jpg)
    renderizada em blocos RGB 24-bit TrueColor (▀).
    """
    return list(SUNTZU_WIKI_22X22)


SUNTZU_QUOTES: Dict[str, List[str]] = {
    "opening": [
        "«A vitória é conquistada no templo antes mesmo de a batalha começar.» — Cap. I",
        "«Quem chega primeiro ao campo de batalha aguarda o inimigo descansado.» — Cap. VI",
        "«No sistema 3-1-0, a abertura é o terreno onde plantamos o desequilíbrio.» — Cap. I",
    ],
    "ponderhit": [
        "«Conhece o teu inimigo e conhece-te a ti mesmo: eu já previa este lance!» — Cap. III",
        "«O general sábio lê o movimento do adversário antes que a peça toque a casa.» — Cap. XIII",
    ],
    "pressao": [
        "«Ofereça uma isca para atrair o inimigo; mantenha-o sob pressão até que erre!» — Cap. I",
        "«Ataque onde ele não está preparado; apareça onde menos se espera.» — Cap. I",
        "«Subjugar o inimigo mantendo a tensão máxima é a verdadeira excelência.» — Cap. III",
    ],
    "virada": [
        "«Em terreno de morte, lute com todas as forças! Na confusão nasce a virada!» — Cap. XI",
        "«Quando cercado, teça armadilhas; aparente fraqueza e prepare a emboscada!» — Cap. I",
        "«No caos aparente das complicações, a ordem tática espreita o erro fatal.» — Cap. V",
    ],
    "conversao": [
        "«O estrategista vitorioso só trava o combate depois que a vitória está garantida.» — Cap. IV",
        "«Simplifique o campo de batalha e corte todas as rotas de contra-ataque.» — Cap. VII",
        "«Quando a vantagem é clara, avance com a precisão implacável da montanha.» — Cap. IV",
    ],
    "capture_check": [
        "«Que o teu ataque seja veloz como o vento e devastador como o trovão!» — Cap. VII",
        "«Golpeie o ponto vital do exército inimigo com a força de uma torrente!» — Cap. V",
    ],
    "panic": [
        "«A velocidade é a essência da guerra! Mova a peça e acione o relógio sem hesitar!» — Cap. II",
        "«O tempo é a nossa muralha: execute o lance no tabuleiro físico imediatamente!» — Cap. II",
    ],
    "draw_claim": [
        "«Aquele que sabe quando lutar e quando recuar sairá vitorioso. Reivindique o empate!» — Cap. III",
    ],
    "draw_refuse": [
        "«Três pontos valem três empates! Não conceda trégua quando temos a iniciativa!» — Cap. IV",
    ],
    "default": [
        "«Seja sutil até parecer invisível; seja misterioso até parecer inaudível.» — Cap. VI",
        "«Na guerra, os números sozinhos não dão vantagem; a harmonia das peças decide.» — Cap. IX",
        "«O exército vitorioso é como a água: adapta a sua forma ao terreno do inimigo.» — Cap. VI",
    ],
}


def select_suntzu_quote_and_mood(
    board: chess.Board,
    suntzu_info: str,
    last_move_info: Optional[Dict[str, object]],
    used_ponderhit: bool,
    from_book: bool,
    our_time_ms: int,
    last_eval_cp: Optional[int],
    rule_alerts: List[str],
) -> Tuple[str, str, str]:
    """
    Retorna (frase, mood, titulo_estado) baseado no momento exato da partida.
    """
    ply = len(board.move_stack)
    idx = ply % 3

    if any("REIVINDIQUE O EMPATE" in a for a in rule_alerts):
        return SUNTZU_QUOTES["draw_claim"][0], "swindle", "RECUO TÁTICO (EMPATE)"

    if any("NÃO REIVINDIQUE" in a for a in rule_alerts):
        return SUNTZU_QUOTES["draw_refuse"][0], "attack", "RECUSA DE EMPATE 3-1-0"

    if our_time_ms < 180_000:
        q = SUNTZU_QUOTES["panic"][ply % len(SUNTZU_QUOTES["panic"])]
        return q, "panic", "RESERVA DE PÂNICO"

    if used_ponderhit:
        q = SUNTZU_QUOTES["ponderhit"][ply % len(SUNTZU_QUOTES["ponderhit"])]
        return q, "ponderhit", "ANTECIPAÇÃO (PONDERHIT)"

    if from_book or ply <= 4:
        q = SUNTZU_QUOTES["opening"][ply % len(SUNTZU_QUOTES["opening"])]
        return q, "normal", "ABERTURA (LIVRO 3-1-0)"

    if "modo=virada" in suntzu_info or (last_eval_cp is not None and last_eval_cp <= -150):
        q = SUNTZU_QUOTES["virada"][ply % len(SUNTZU_QUOTES["virada"])]
        return q, "swindle", "MODO VIRADA (SWINDLE)"

    if "modo=conversao" in suntzu_info or (last_eval_cp is not None and last_eval_cp >= 300):
        q = SUNTZU_QUOTES["conversao"][ply % len(SUNTZU_QUOTES["conversao"])]
        return q, "convert", "MODO CONVERSÃO"

    if "modo=pressao" in suntzu_info:
        q = SUNTZU_QUOTES["pressao"][ply % len(SUNTZU_QUOTES["pressao"])]
        return q, "attack", "MODO PRESSÃO ATIVO"

    if last_move_info and (last_move_info.get("gives_check") or last_move_info.get("is_capture")):
        q = SUNTZU_QUOTES["capture_check"][ply % len(SUNTZU_QUOTES["capture_check"])]
        return q, "attack", "GOLPE TÁTICO"

    q = SUNTZU_QUOTES["default"][idx]
    return q, "normal", "DOUTRINA SUN TZU"


def wrap_text(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------------------------------------------------------------------------
# Renderização do Tabuleiro Colorido + Barra de Avaliação
# ---------------------------------------------------------------------------

def render_colored_board_lines(
    board: chess.Board,
    perspective: chess.Color = chess.WHITE,
    eval_cp: Optional[int] = None,
    pending_move: Optional[chess.Move] = None,
) -> List[str]:
    """
    Gera 20 linhas do tabuleiro colorido com coordenadas grandes, destaque da casa
    de origem/destino do último lance e barra de avaliação lateral.
    """
    ranks = range(7, -1, -1) if perspective == chess.WHITE else range(0, 8)
    files = range(0, 8) if perspective == chess.WHITE else range(7, -1, -1)
    file_header = "     " + "".join(f"  {chess.FILE_NAMES[f].upper()}  " for f in files) + "    "

    last_move = board.peek() if board.move_stack else None
    hl_squares = {last_move.from_square, last_move.to_square} if last_move else set()
    pending_squares = {pending_move.from_square, pending_move.to_square} if pending_move else set()
    king_in_check_sq = board.king(board.turn) if board.is_check() else None

    cp = 0 if eval_cp is None else max(-800, min(800, eval_cp))
    filled_rows = int(round(((cp + 800) / 1600.0) * 16))
    filled_rows = max(1, min(15, filled_rows))

    lines: List[str] = []
    lines.append(f"{GOLD}{BOLD}{file_header}{RESET}")
    lines.append(f"   {MUTED}╔{'═════' * 8}╗{RESET} {MUTED}┬─┬{RESET}")

    row_counter = 0
    for r in ranks:
        top_cells: List[str] = []
        bot_cells: List[str] = []
        for f in files:
            sq = chess.square(f, r)
            is_light = (r + f) % 2 == 1
            if sq == king_in_check_sq:
                bg = BG_CHECK_SQ
            elif sq in pending_squares:
                bg = BG_PENDING_SQ
            elif sq in hl_squares:
                bg = BG_HIGHLIGHT_LIGHT if is_light else BG_HIGHLIGHT_DARK
            else:
                bg = BG_LIGHT_SQ if is_light else BG_DARK_SQ

            piece = board.piece_at(sq)
            if piece is not None:
                fg = FG_WHITE_PIECE if piece.color == chess.WHITE else FG_BLACK_PIECE
                sym = UNICODE_PIECES[(piece.piece_type, piece.color)]
                let = PT_LETTER[piece.piece_type]
                if piece.color == chess.BLACK:
                    let = let.lower()
                top_cells.append(f"{bg}{fg} {sym} {let} {RESET}")
            else:
                dot = "·" if (sq in hl_squares or sq in pending_squares) else " "
                fg_dot = fg_rgb(90, 75, 45) if is_light else fg_rgb(175, 145, 105)
                top_cells.append(f"{bg}{fg_dot}  {dot}  {RESET}")

            sq_tag = f"{chess.FILE_NAMES[f]}{r + 1}" if (sq in hl_squares or sq in pending_squares) else "  "
            tag_fg = fg_rgb(65, 55, 20) if is_light else fg_rgb(230, 215, 175)
            bot_cells.append(f"{bg}{tag_fg}   {sq_tag}{RESET}")

        bar_idx_top = 15 - row_counter
        bar_idx_bot = 15 - (row_counter + 1)
        bar_top = (
            f"{bg_rgb(72, 200, 125)} {RESET}"
            if bar_idx_top < filled_rows
            else f"{bg_rgb(75, 80, 92)} {RESET}"
        )
        bar_bot = (
            f"{bg_rgb(72, 200, 125)} {RESET}"
            if bar_idx_bot < filled_rows
            else f"{bg_rgb(75, 80, 92)} {RESET}"
        )
        row_counter += 2

        rank_lbl = f"{GOLD}{BOLD} {r + 1} {RESET}"
        lines.append(f"{rank_lbl}{MUTED}║{RESET}{''.join(top_cells)}{MUTED}║{RESET} {MUTED}│{RESET}{bar_top}{MUTED}│{RESET}")
        lines.append(f"   {MUTED}║{RESET}{''.join(bot_cells)}{MUTED}║{RESET} {MUTED}│{RESET}{bar_bot}{MUTED}│{RESET}")

    eval_str = f"{cp / 100.0:+.2f}" if eval_cp is not None else "0.00"
    lines.append(f"   {MUTED}╚{'═════' * 8}╝{RESET} {GOLD}{eval_str:>4}{RESET}")
    lines.append(f"{GOLD}{BOLD}{file_header}{RESET}")
    return lines


# ---------------------------------------------------------------------------
# Painel Completo TUI (Tabuleiro à Esquerda + General Sun Tzu e Telemetria à Direita)
# ---------------------------------------------------------------------------

def parse_suntzu_telemetry(info_str: str) -> Dict[str, str]:
    """Extrai os campos de `info string SunTzu: ...` para exibição organizada."""
    res = {
        "perfil": "AUTO (CALIBRANDO)",
        "perda_ema": "0.0cp",
        "amostras": "0",
        "draw_aversion": "20cp",
        "modo": "NENHUM",
        "motivo": "padrao",
        "selecao": "",
    }
    if not info_str:
        return res

    m_perf = re.search(r"perfil=([^\s(]+)", info_str)
    if m_perf:
        res["perfil"] = m_perf.group(1).upper()
    m_ema = re.search(r"perda_ema=([^,)]+)", info_str)
    if m_ema:
        res["perda_ema"] = m_ema.group(1)
    m_am = re.search(r"amostras=(\d+)", info_str)
    if m_am:
        res["amostras"] = m_am.group(1)
    m_da = re.search(r"DrawAversion=([^,)]+)", info_str)
    if m_da:
        res["draw_aversion"] = m_da.group(1)
    m_modo = re.search(r"modo=([^,)]+)", info_str)
    if m_modo:
        res["modo"] = m_modo.group(1).upper()
    m_mot = re.search(r"motivo=([^,)]+)", info_str)
    if m_mot:
        res["motivo"] = m_mot.group(1)
    if "selecao=" in info_str:
        res["selecao"] = info_str.split("selecao=", 1)[1]
    return res


def format_mmss_colored(ms: int, is_our: bool) -> str:
    sec = max(0, int(round(ms / 1000.0)))
    m, s = divmod(sec, 60)
    txt = f"{m:02d}:{s:02d}"
    if is_our and sec < 120:
        return f"{ALERT_BG} {txt} (PÂNICO!) {RESET}"
    if is_our and sec < 300:
        return f"{CRIMSON}{BOLD}{txt}{RESET}"
    return f"{JADE if is_our else SILVER}{BOLD}{txt}{RESET}"


def format_move_history_compact(board: chess.Board, max_lines: int = 2, width: int = 58) -> List[str]:
    """Formata os últimos lances em notação PGN (PT) para o painel lateral."""
    temp = chess.Board()
    pairs: List[str] = []
    moves = list(board.move_stack)
    for i in range(0, len(moves), 2):
        m_num = (i // 2) + 1
        w_mv = moves[i]
        w_san = _san_pt_short(temp, w_mv)
        temp.push(w_mv)
        if i + 1 < len(moves):
            b_mv = moves[i + 1]
            b_san = _san_pt_short(temp, b_mv)
            temp.push(b_mv)
            pairs.append(f"{m_num}.{w_san} {b_san}")
        else:
            pairs.append(f"{m_num}.{w_san}")

    if not pairs:
        return [f"{MUTED}(Partida no lance inicial){RESET}"]

    joined = "  ".join(pairs[-10:])
    wrapped = wrap_text(joined, width)
    return wrapped[-max_lines:]


def _san_pt_short(board: chess.Board, move: chess.Move) -> str:
    san = board.san(move)
    out = []
    for ch in san:
        out.append({"N": "C", "B": "B", "R": "T", "Q": "D", "K": "R"}.get(ch, ch))
    return "".join(out)


def render_dashboard(
    board: chess.Board,
    our_color: chess.Color,
    our_time_ms: int,
    opp_time_ms: int,
    suntzu_info: str,
    last_eval_cp: Optional[int],
    last_our_move_info: Optional[Dict[str, object]],
    last_origin_tag: str,
    ponder_move_uci: Optional[str],
    used_ponderhit: bool,
    from_book: bool,
    rule_alerts: List[str],
    pending_opp_move: Optional[chess.Move] = None,
    pending_opp_info: Optional[Dict[str, object]] = None,
    status_flash: str = "",
    clear_screen: bool = True,
) -> str:
    """
    Constrói o painel TUI completo (lado a lado se o terminal tiver >= 108 colunas,
    ou empilhado com elegância em terminais menores).
    """
    out: List[str] = []
    if clear_screen:
        out.append("\x1b[2J\x1b[H")

    cols = int(os.environ.get("COLUMNS", 0)) or shutil.get_terminal_size((120, 36)).columns
    our_side_str = "BRANCAS (♔)" if our_color == chess.WHITE else "PRETAS (♚)"
    turn_str = (
        f"{JADE}{BOLD}NOSSA VEZ{RESET}"
        if board.turn == our_color
        else f"{BRIGHT_GOLD}{BOLD}AGUARDANDO LANCE DO ADVERSÁRIO{RESET}"
    )

    header_w = min(max(cols - 2, 78), 116)
    title = " ⚔  S U N T Z U   —   C O N S O L E   D E   G U E R R A   (I C E V   2 0 2 6)  ⚔ "
    out.append(f"{GOLD}{BOLD}╔{'═' * header_w}╗{RESET}")
    out.append(f"{GOLD}{BOLD}║{BRIGHT_GOLD}{title.center(header_w)}{GOLD}║{RESET}")
    out.append(f"{GOLD}{BOLD}╚{'═' * header_w}╝{RESET}")

    quote, mood, state_title = select_suntzu_quote_and_mood(
        board=board,
        suntzu_info=suntzu_info,
        last_move_info=last_our_move_info,
        used_ponderhit=used_ponderhit,
        from_book=from_book,
        our_time_ms=our_time_ms,
        last_eval_cp=last_eval_cp,
        rule_alerts=rule_alerts,
    )
    portrait = get_suntzu_portrait_lines(mood)
    telem = parse_suntzu_telemetry(suntzu_info)

    bubble_inner_w = 36
    q_lines = wrap_text(quote, bubble_inner_w - 2)
    while len(q_lines) < 4:
        q_lines.append("")

    hdr_label = f"─ ✦ SUN TZU: {state_title} "
    if len(hdr_label) > bubble_inner_w:
        hdr_label = hdr_label[:bubble_inner_w]
    dashes_after = max(0, bubble_inner_w - len(hdr_label))

    right_lines: List[str] = []
    right_lines.append(
        f"{portrait[0]}  {GOLD}{BOLD}╭{hdr_label}{'─' * dashes_after}╮{RESET}"
    )
    right_lines.append(
        f"{portrait[1]}  {GOLD}│{RESET} {BRIGHT_GOLD}{pad_ansi(q_lines[0], bubble_inner_w - 2)}{RESET} {GOLD}│{RESET}"
    )
    right_lines.append(
        f"{portrait[2]}  {GOLD}│{RESET} {BRIGHT_GOLD}{pad_ansi(q_lines[1], bubble_inner_w - 2)}{RESET} {GOLD}│{RESET}"
    )
    right_lines.append(
        f"{portrait[3]}  {GOLD}‹{RESET} {BRIGHT_GOLD}{pad_ansi(q_lines[2], bubble_inner_w - 2)}{RESET} {GOLD}│{RESET}"
    )
    right_lines.append(
        f"{portrait[4]}  {GOLD}│{RESET} {BRIGHT_GOLD}{pad_ansi(q_lines[3], bubble_inner_w - 2)}{RESET} {GOLD}│{RESET}"
    )
    right_lines.append(f"{portrait[5]}  {GOLD}╰{'─' * bubble_inner_w}╯{RESET}")
    right_lines.append(
        f"{portrait[6]}  {SILVER}✦ Cor SunTzu   :{RESET} {WHITE_FG}{BOLD}{our_side_str}{RESET} | {turn_str}"
    )
    right_lines.append(
        f"{portrait[7]}  {SILVER}◷ Nosso Relógio:{RESET} {format_mmss_colored(our_time_ms, True)}"
        f"   {SILVER}Oponente:{RESET} {format_mmss_colored(opp_time_ms, False)}"
    )
    ponder_txt = (
        f"{CYAN}{BOLD}Ativo em '{ponder_move_uci}'{RESET}"
        if ponder_move_uci
        else f"{MUTED}Inativo / Aguardando{RESET}"
    )
    right_lines.append(f"{portrait[8]}  {SILVER}◈ Ponder       :{RESET} {ponder_txt}")
    right_lines.append(
        f"{portrait[9]}  {SILVER}◎ Perfil Opon. :{RESET} {GOLD}{BOLD}{telem['perfil']}{RESET} "
        f"{MUTED}(EMA={telem['perda_ema']}, n={telem['amostras']}){RESET}"
    )
    modo_color = (
        CRIMSON
        if telem["modo"] in ("PRESSAO", "VIRADA")
        else (JADE if telem["modo"] == "CONVERSAO" else SILVER)
    )
    right_lines.append(
        f"{portrait[10]}  {SILVER}⚔ Modo Tático  :{RESET} {modo_color}{BOLD}{telem['modo']}{RESET} "
        f"{MUTED}| DrawAversion={telem['draw_aversion']}{RESET}"
    )

    # Linhas 11..19: Banner do Nosso Último Lance (ou Confirmação de Lance) + Histórico PGN
    right_lines.append(f"{GOLD}──────────────────────────────────────────────────────────────{RESET}")
    if pending_opp_info is not None:
        san_p = str(pending_opp_info.get("san", ""))
        f_sq = str(pending_opp_info.get("from_sq", ""))
        t_sq = str(pending_opp_info.get("to_sq", ""))
        spoken_p = str(pending_opp_info.get("spoken", ""))
        right_lines.append(
            f"{CONFIRM_BG}  ? CONFIRMAR LANCE DO ADVERSÁRIO: {san_p} ({f_sq} -> {t_sq}) ?  {RESET}"
        )
        right_lines.append(
            f"  {WHITE_FG}{BOLD}Movimento:{RESET} {spoken_p} {CYAN}(destacado em azul no tabuleiro){RESET}"
        )
        right_lines.append(
            f"  {BRIGHT_GOLD}{BOLD}Pressione [ENTER] para confirmar ou digite 'n' para cancelar.{RESET}"
        )
    elif last_our_move_info is not None:
        san_str = str(last_our_move_info.get("san", ""))
        f_sq = str(last_our_move_info.get("from_sq", ""))
        t_sq = str(last_our_move_info.get("to_sq", ""))
        spoken = str(last_our_move_info.get("spoken", ""))
        alerts = list(last_our_move_info.get("alerts", []))  # type: ignore
        right_lines.append(
            f"{BANNER_BG}  >>> NOSSO LANCE NO TABULEIRO:  {san_str}  ({f_sq} -> {t_sq}) <<<  {RESET}"
        )
        right_lines.append(
            f"  {WHITE_FG}{BOLD}Ditar:{RESET} {spoken} "
            f"{MUTED}[ UCI: {last_our_move_info.get('uci', '')} | {last_origin_tag} ]{RESET}"
        )
        if alerts:
            alert_line = " | ".join(alerts)
            right_lines.append(f"  {ALERT_BG} !!! {alert_line} !!! {RESET}")
        else:
            right_lines.append(
                f"  {JADE}✓ Lance limpo (sem captura/xeque). Mova a peça e acione o relógio.{RESET}"
            )
    else:
        right_lines.append(f"  {MUTED}[ Aguardando o 1º lance da partida... ]{RESET}")
        right_lines.append("")
        right_lines.append("")

    right_lines.append(f"{GOLD}──────────────────────────────────────────────────────────────{RESET}")
    hist_lines = format_move_history_compact(board, max_lines=2, width=58)
    right_lines.append(f"  {SILVER}{BOLD}Histórico PGN ({len(board.move_stack)} meios-lances):{RESET}")
    for hl in hist_lines:
        right_lines.append(f"  {WHITE_FG}{hl}{RESET}")
    if status_flash:
        right_lines.append(f"  {BRIGHT_GOLD}{BOLD}⚡ {status_flash}{RESET}")
    while len(right_lines) < 20:
        right_lines.append("")

    board_to_draw = board.copy()
    if pending_opp_move is not None:
        board_to_draw.push(pending_opp_move)

    board_lines = render_colored_board_lines(
        board_to_draw,
        perspective=our_color,
        eval_cp=last_eval_cp,
        pending_move=pending_opp_move,
    )

    if cols >= 105:
        for b_line, r_line in zip(board_lines, right_lines):
            out.append(f"{pad_ansi(b_line, 54)}  {r_line}")
    else:
        out.extend(board_lines)
        out.append("")
        out.extend(right_lines)

    if rule_alerts:
        out.append("")
        for ra in rule_alerts:
            out.append(f"  {ALERT_BG} {ra} {RESET}")

    out.append(
        f"{GOLD}┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐{RESET}"
    )
    out.append(
        f"{GOLD}│{RESET} {BOLD}Comandos:{RESET} Lance ({CYAN}e4{RESET}, {CYAN}Cf6{RESET}, {CYAN}Cxf7{RESET}, {CYAN}0-0{RESET}, {CYAN}e2e4{RESET}) "
        f"│ {BRIGHT_GOLD}u{RESET}=Desfazer │ {BRIGHT_GOLD}t 18:30{RESET}=Relógio │ {BRIGHT_GOLD}perfil fraco{RESET} │ {BRIGHT_GOLD}rapido{RESET} │ {BRIGHT_GOLD}quit{RESET} {GOLD}│{RESET}"
    )
    out.append(
        f"{GOLD}└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘{RESET}"
    )
    res = "\n".join(out)
    if clear_screen:
        if cols >= 105:
            res += _get_kitty_png_escape(row=4, col=57, cols_w=22, rows_h=11)
        else:
            res += _get_kitty_png_escape(row=25, col=1, cols_w=22, rows_h=11)
    return res
