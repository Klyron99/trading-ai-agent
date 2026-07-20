""" Documentation complète du site et de l'agent.
"""
from __future__ import annotations
import streamlit as st

_BG     = "#080c14"
_CARD   = "#0f1724"
_GRID   = "#1a2235"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_GREEN  = "#10b981"
_RED    = "#f43f5e"
_BLUE   = "#3b82f6"
_ORANGE = "#f59e0b"


def _section(title: str, icon: str = ""):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'margin:36px 0 16px;padding-bottom:10px;border-bottom:2px solid {_GRID};">'
        f'<span style="font-size:20px;">{icon}</span>'
        f'<span style="font-size:13px;font-weight:700;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:{_MUTED};">{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _card(title: str, content: str, color: str = _BLUE):
    st.markdown(
        f'<div style="background:{_CARD};border:1px solid {_GRID};border-left:3px solid {color};'
        f'border-radius:8px;padding:16px 20px;margin-bottom:12px;">'
        f'<div style="font-weight:700;color:{_TEXT};margin-bottom:8px;font-size:14px;">{title}</div>'
        f'<div style="color:{_MUTED};font-size:13px;line-height:1.7;">{content}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _tip(text: str):
    st.markdown(
        f'<div style="background:rgba(41,98,255,0.08);border:1px solid rgba(41,98,255,0.25);'
        f'border-radius:8px;padding:10px 16px;margin-bottom:8px;'
        f'font-size:13px;color:{_TEXT};line-height:1.6;">'
        f'💡 {text}</div>',
        unsafe_allow_html=True,
    )


def _warning(text: str):
    st.markdown(
        f'<div style="background:rgba(255,152,0,0.08);border:1px solid rgba(255,152,0,0.3);'
        f'border-radius:8px;padding:10px 16px;margin-bottom:8px;'
        f'font-size:13px;color:{_TEXT};line-height:1.6;">'
        f'-s-️ {text}</div>',
        unsafe_allow_html=True,
    )


def _step(num: int, title: str, desc: str):
    st.markdown(
        f'<div style="display:flex;gap:14px;margin-bottom:14px;align-items:flex-start;">'
        f'<div style="min-width:28px;height:28px;background:{_BLUE};border-radius:50%;'
        f'display:flex;align-items:center;justify-content:center;'
        f'font-size:12px;font-weight:800;color:white;flex-shrink:0;">{num}</div>'
        f'<div>'
        f'<div style="font-weight:700;color:{_TEXT};font-size:13px;margin-bottom:3px;">{title}</div>'
        f'<div style="color:{_MUTED};font-size:12px;line-height:1.6;">{desc}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _badge(label: str, color: str):
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}66;'
        f'border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;'
        f'margin-right:4px;">{label}</span>'
    )


def render(ticker: str = "BTC-USD", **kwargs):

    st.markdown(
        f'<h2 style="color:{_TEXT};font-weight:800;margin-bottom:4px;font-size:26px;">Guide d\'utilisation</h2>'
        f'<div style="color:{_MUTED};font-size:13px;margin-bottom:8px;">'
        f'Tout ce qu\'il faut savoir pour utiliser l\'agent et le site correctement</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="background:rgba(38,166,154,0.08);border:1px solid rgba(38,166,154,0.3);'
        f'border-radius:8px;padding:12px 18px;margin-bottom:24px;font-size:13px;color:{_TEXT};">'
        f'<b>Rappel de sécurité :</b> Ce site est en <b>paper trading uniquement</b>. '
        f'Aucun vrai argent n\'est utilisé. Tous les trades sont simulés.</div>',
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Démarrage rapide",
        "L'agent",
        "Les pages",
        "Reglages avances",
        "FAQ",
    ])

    # -"?-"? TAB 1 : Démarrage rapide -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    with tab1:
        st.markdown(f'<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:15px;font-weight:700;color:{_TEXT};margin-bottom:16px;">En 5 étapes pour démarrer</div>', unsafe_allow_html=True)

        _step(1, "Aller dans Contrôles -?' Réentraîner les modèles ML",
              "Sélectionne BTC-USD (déjà coché par défaut) et clique sur 'Lancer le réentraînement'. "
              "Cela prend 1-3 minutes. Le modèle se met à jour et la version passe à v5, v6...")

        _step(2, "Choisir le ticker et l'intervalle",
              "Dans la section 'Démarrer l'agent', sélectionne BTC-USD (recommandé car disponible 24h/24) "
              "et un intervalle de 60 secondes (1 décision par minute).")

        _step(3, "Lancer l'agent",
              "Clique sur '--- Démarrer l'agent'. Il apparaît en vert dans la sidebar avec un chronomètre. "
              "La première décision arrive dans les 30 secondes.")

        _step(4, "Surveiller les décisions",
              "Va sur la page 'Décisions' pour voir en temps réel chaque BUY / SELL / HOLD "
              "avec le grade (A/B/C/D) et la raison. La page se rafraîchit toutes les 10 secondes.")

        _step(5, "Réentraîner régulièrement",
              "Toutes les 6 heures environ, le modèle peut être réentraîné pour s'adapter aux nouvelles données. "
              "Tu peux aussi le faire manuellement depuis Contrôles à tout moment, même quand l'agent tourne.")

        _tip("pas de fermeture de marché le week-end.")
        _warning("Ne lance jamais 2 agents en même temps. Si tu relances depuis Contrôles, l'ancien est automatiquement tué.")

    # -"?-"? TAB 2 : L'agent -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    with tab2:
        st.markdown(f'<div style="margin-top:20px;"></div>', unsafe_allow_html=True)

        _section("Comment l'agent prend ses décisions", "🤖")

        st.markdown(
            f'<div style="color:{_MUTED};font-size:13px;line-height:1.8;margin-bottom:16px;">'
            f'-? chaque tick (toutes les 60s par défaut), l\'agent fait 4 choses :'
            f'</div>', unsafe_allow_html=True
        )

        _card("Télécharge les données de marché",
              "Récupère 6 mois de données OHLCV (Open/High/Low/Close/Volume) via yFinance pour calculer les indicateurs techniques.")

        _card("Génère un signal technique",
              "La stratégie active (SMA, RSI, MACD ou ML) analyse les données et produit un signal : "
              "<b style='color:#26a69a'>+1 (Haussier)</b>, <b style='color:#ef5350'>-1 (Baissier)</b> ou <b style='color:#787b86'>0 (Neutre)</b>.")

        _card("Calcule la confiance ML",
              "Le modèle RandomForest prédit la probabilité de hausse (0% à 100%). "
              "Si la confiance est <b>-?- 60%</b>, le signal est considéré fiable.")

        _card("Décide et exécute",
              "Combine signal + confiance ML pour décider BUY / SELL / HOLD, vérifie les règles de risque, "
              "puis enregistre la décision et exécute le trade en simulation.")

        _section("Le système de grades", "🏆")

        cols = st.columns(4)
        grades = [
            ("A", _GREEN, ">= 80%", "trade immédiat même si récent"),
            ("B", _BLUE, ">= 65%", "trade immédiat"),
            ("C", _ORANGE, ">= 60%", "attend 20 min si HOLD récent"),
            ("D", _RED, "< 60%", "attend 20 min obligatoire"),
        ]
        for col, (g, c, pct, desc) in zip(cols, grades):
            with col:
                st.markdown(
                    f'<div style="background:{_CARD};border:1px solid {_GRID};border-top:3px solid {c};'
                    f'border-radius:8px;padding:14px;text-align:center;">'
                    f'<div style="font-size:28px;font-weight:800;color:{c};">{g}</div>'
                    f'<div style="font-size:11px;color:{c};font-weight:700;margin:4px 0;">{pct}</div>'
                    f'<div style="font-size:11px;color:{_MUTED};line-height:1.5;">{desc}</div>'
                    f'</div>', unsafe_allow_html=True
                )

        _section("Le forçage de trade", "⏱")
        _card("Pourquoi l'agent force un trade après 20 minutes ?",
              "Si l'agent reste en HOLD trop longtemps (grade C/D), il finit par forcer un signal "
              "dans la direction indiquée par le ML ou la stratégie. Cela évite qu'il reste inactif des heures. "
              "Les grades A/B peuvent trader immédiatement, même 1 seconde après le trade précédent.")

        _tip("l'agent a décidé de ne plus attendre.")

        _section("Les stratégies disponibles", "⚙")
        strats = [
            ("SMA (Moyenne Mobile)", "Croise une MA courte (20) avec une longue (50). Signal haussier quand la rapide passe au-dessus."),
            ("RSI (Relative Strength Index)", "Mesure la force du mouvement. Survente < 30 -?' BUY, Surachat > 70 -?' SELL."),
            ("MACD", "Différence entre 2 moyennes exponentielles. Croisement de la ligne de signal -?' BUY ou SELL."),
            ("ML RandomForest", "Modèle d'apprentissage automatique entraîné sur les données historiques. Prédit la direction via des features techniques."),
        ]
        for name, desc in strats:
            _card(name, desc)

    # -"?-"? TAB 3 : Les pages -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    with tab3:
        st.markdown(f'<div style="margin-top:20px;"></div>', unsafe_allow_html=True)

        pages = [
            ("🤖", "Accueil", _GREEN,
             "Vue en temps réel de l'agent : statut, cours live, dernière décision, confiance ML, évolution du portefeuille simulé. "
             "Se rafraîchit automatiquement toutes les 5 secondes."),
            ("🎮", "Contrôles", _BLUE,
             "Panneau de commande principal. Démarre/arrête l'agent, choisit le ticker et l'intervalle, "
             "lance un réentraînement du modèle ML, vide le cache. "
             "Affiche aussi la version du modèle et l'historique des réentraînements."),
            ("🌍", "Marchés", _MUTED,
             "Aperçu des marchés en temps réel : cours de BTC-USD, AAPL, MSFT, SPY et autres tickers. "
             "Utile pour avoir une vue globale avant de lancer l'agent."),
            ("📈", "Performance", _GREEN,
             "Analyse des résultats de l'agent : courbe de capital simulé, taux de réussite, P&L par trade, "
             "distribution de la confiance ML, historique des trades complets (BUY-?'SELL)."),
            ("📋", "Décisions", _BLUE,
             "Historique complet de toutes les décisions avec grade, confiance, stratégie, prix et raison. "
             "Filtrable par action ou stratégie. Se rafraîchit toutes les 10 secondes. "
             "Bouton 'Effacer' pour repartir à zéro."),
            ("📊", "Stratégies", _ORANGE,
             "Compare les performances historiques de chaque stratégie (SMA, RSI, MACD, ML) via backtest. "
             "Permet de comprendre pourquoi l'agent a choisi telle ou telle stratégie."),
            ("📄", "Logs", _MUTED,
             "Logs bruts de l'agent en temps réel : chaque tick, chaque erreur, chaque trade. "
             "Indispensable pour déboguer un comportement inattendu."),
            ("⚙️", "Paramètres", _MUTED,
             "Configuration avancée : clés API Alpaca, capital initial, drawdown maximum, tickers autorisés."),
        ]

        for icon, name, color, desc in pages:
            st.markdown(
                f'<div style="background:{_CARD};border:1px solid {_GRID};border-left:3px solid {color};'
                f'border-radius:8px;padding:14px 18px;margin-bottom:10px;display:flex;gap:14px;">'
                f'<div style="font-size:22px;flex-shrink:0;">{icon}</div>'
                f'<div><div style="font-weight:700;color:{_TEXT};font-size:14px;margin-bottom:4px;">{name}</div>'
                f'<div style="color:{_MUTED};font-size:12px;line-height:1.7;">{desc}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # -"?-"? TAB 4 : Réglages avancés -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    with tab4:
        st.markdown(f'<div style="margin-top:20px;"></div>', unsafe_allow_html=True)

        _section("Seuils de confiance", "🎮")
        _card("Seuil minimum de confiance ML (60%)",
              "L'agent trade uniquement si la confiance ML est -?- 60%. En dessous, il reste en HOLD "
              "(sauf si le forçage 20 min se déclenche). Tu peux modifier ce seuil dans <b>config/settings.py</b> "
              "via la variable <code style='color:#2962ff'>AGENT_MIN_CONFIDENCE</code>.")

        _tip("Baisser le seuil à 0.50 rend l'agent beaucoup plus actif mais prend plus de risques. "
             "Le monter à 0.65 le rend très sélectif mais il tradera moins souvent.")

        _section("Intervalle de décision", "⏱")
        _card("60 secondes par défaut",
              "L'agent prend une décision toutes les 60 secondes. Tu peux choisir 30s (plus réactif), "
              "120s, 300s ou 600s dans Contrôles. Un intervalle court = plus de décisions mais plus de charge CPU.")

        _section("Drawdown maximum", "")
        _card("Arrêt automatique si perte > 15%",
              "Si le portefeuille simulé perd plus de 15% par rapport à son pic, l'agent s'arrête automatiquement "
              "pour protéger le capital. Configurable via <code style='color:#2962ff'>AGENT_MAX_DRAWDOWN</code> dans settings.py.")

        _section("Réentraînement automatique", "")
        _card("Toutes les 6 heures",
              "L'agent peut se réentraîner automatiquement. Chaque réentraînement compare le nouveau modèle "
              "avec l'ancien et garde le meilleur. La version (v1, v2-?-) s'incrémente à chaque réentraînement réussi.")

        _warning("Si tu réentraînes trop souvent sur peu de données (< 1000 points), le modèle peut se dégrader. "
                 "Une fois par jour est idéal pour BTC-USD.")

        _section("Choix du ticker", "'-")
        _card("Pourquoi BTC-USD est recommandé",
              "pas de fermeture de marché. Les actions US (AAPL, SPY) "
              "ne tradent que du lundi au vendredi de 15h30 à 22h00 heure française. "
              "En dehors de ces horaires, l'agent reste en HOLD car les données sont gelées.")

    # -"?-"? TAB 5 : FAQ -"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?-"?
    with tab5:
        st.markdown(f'<div style="margin-top:20px;"></div>', unsafe_allow_html=True)

        faqs = [
            ("L'agent reste en HOLD depuis longtemps, c'est normal ?",
             f"Oui, si le ML est peu confiant (< 60%), l'agent attend. Après 20 minutes de HOLD, il force un trade "
             f"dans la direction indiquée par le ML. Si tu veux plus d'activité, baisse le seuil de confiance ou "
             f"réentraîne le modèle.",
             _BLUE),

            ("Le réentraînement affiche une erreur mais le modèle a changé de version ?",
             f"C'est un bug d'affichage corrigé. Si la version a augmenté, le réentraînement a bien fonctionné. "
             f"Le message est maintenant toujours vert en cas de succès.",
             _GREEN),

            ("Pourquoi 2 agents peuvent tourner en même temps ?",
             f"Si Streamlit est relancé ou si le bouton Démarrer est cliqué plusieurs fois, un ancien processus "
             f"peut rester. La page Contrôles tue automatiquement les anciens agents avant d'en lancer un nouveau. "
             f"En cas de doute, clique 'Arrêter l'agent' puis 'Démarrer l'agent'.",
             _ORANGE),

            ("Les heures affichées sont en retard ?",
             f"Les données sont stockées en UTC dans la base. Le site ajoute automatiquement +2h (heure française UTC+2) "
             f"pour l'affichage. Si tu es dans un autre fuseau, contacte le développeur.",
             _BLUE),

            ("Puis-je utiliser ce site sur téléphone ?",
             f"Oui, le site est optimisé pour mobile. La sidebar se cache automatiquement sur petit écran. "
             f"Utilise le lien ngrok partagé et ouvre-le dans ton navigateur mobile.",
             _GREEN),

            ("Le modèle ML a 49% d'accuracy, c'est mauvais ?",
             f"Pas nécessairement. En finance, 50-60% d'accuracy est déjà rentable si les gains sont plus grands "
             f"que les pertes. L'agent combine ML + indicateurs techniques pour améliorer la décision finale.",
             _ORANGE),

            ("Comment savoir quelle stratégie est active ?",
             f"Va sur la page Accueil, la carte 'Stratégie active' en bas à droite affiche la stratégie en cours. "
             f"Tu peux voir l'historique complet dans la page Stratégies.",
             _BLUE),

            ("Peut-on brancher un vrai compte Alpaca ?",
             f"Le système est conçu pour le paper trading uniquement. Des gardes-fous empêchent tout trade réel : "
             f"LIVE_TRADING=false, URL paper-api.alpaca.markets, vérification à chaque ordre. Ne pas modifier ces paramètres.",
             _RED),
        ]

        for q, a, color in faqs:
            with st.expander(q):
                st.markdown(
                    f'<div style="color:{_MUTED};font-size:13px;line-height:1.8;padding:4px 0;">{a}</div>',
                    unsafe_allow_html=True,
                )
