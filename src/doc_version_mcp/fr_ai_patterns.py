"""
fr_ai_patterns.py — Motifs déterministes d'écriture IA pour la langue française.
Transposé depuis le projet avoid-ai-writing-multilingual (SKILL-FR.md).
Source canonique : https://github.com/jurigis/avoid-ai-writing-multilingual
Commit de référence : 4e5aa4c5123061cc7ef6f94147e77182ad8d8e6e (Wed Aug 5 13:22:32 2026)
Auteur de l'adaptation multilingue : Jürgen Kraus (https://github.com/jurigis)
Licence : MIT (Copyright (c) Conor Bronsdon, Copyright (c) 2025 Jürgen Kraus)

Classification rigoureuse :
- P0 : Tue la crédibilité (Tolérance 0 - Hard Blocker immédiat)
- P1 : Forte odeur IA / surreprésentation statistique / collocations clichées (Tolérance 0 - Hard Blocker)
- P2 : Révision stylistique / mots isolés surveillés (Soft Warning - Régulé par budget et répétition)

Couverture de fidélité SKILL-FR.md :
- 38 motifs transposés en règles déterministes (#1, #2, #3, #4, #5, #6, #7, #8, #9, #12, #13, #14,
  #15, #15a, #16, #17, #18, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33,
  #34, #35, #36, #40, #41, #42, #43, #44, #45).
- 7 motifs non transposables par regex statique locale (structurels, statistiques ou méta-règles) :
  • #10 (Chaînes de synonymes) : Sémantique globale / analyse de co-référence requise.
  • #11 (Phrases gabarit) : Analyse morpho-syntaxique (POS tagging) requise.
  • #19 (Uniformité structurelle) : Métrique stylométrique statistique (variance de longueur de phrase).
  • #20 (Puces nominales nues générales) : Détection grammaticale d'absence de verbe conjugué.
  • #37 (Rythme et uniformité) : Doublon statistique du motif #19 (longueur des paragraphes).
  • #38 (Sur-polissage) : Méta-évaluation qualitative humaine de la texture globale.
  • #39 (Seuil réécriture-vs-correction) : Règle décisionnelle méta d'arbitrage du skill.

Règle d'or anti-faux positifs :
Les mots courants du français (essentiel, fondamental, dynamique, harmonie/harmonieux, innovation,
crucial, il apparaît que) sont légitimes lorsqu'ils sont isolés. Seules leurs collocations clichées
multi-mots (« rôle essentiel », « tournant décisif », « écosystème innovant ») sont bloquantes (P1).
Isolés, ils ne déclenchent un avertissement stylistique (P2) qu'en cas de répétition (fréquence >= 2).
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set, Tuple


@dataclass(frozen=True)
class FrenchAIPattern:
    id: str
    level: str  # "P0", "P1", "P2"
    category: str
    pattern: str  # Regex source
    message: str
    suggestion: str


# ============================================================================
# 1. CATALOGUE DES MOTIFS DE RÈGLES DE SKILL-FR.MD
# ============================================================================

FRENCH_AI_PATTERNS: List[FrenchAIPattern] = [
    # -------------------------------------------------------------------------
    # P0 — TUE LA CRÉDIBILITÉ (TOLÉRANCE 0)
    # -------------------------------------------------------------------------
    FrenchAIPattern(
        id="FR-P0-26",
        level="P0",
        category="Ouverture chatbot",
        pattern=r"(?i)\b(?:bien\s+sûr|avec\s+plaisir|absolument|certainement)\s*!|\b(?:je\s+serais\s+ravi[e]?\s+de|c'est\s+avec\s+plaisir\s+que)\b",
        message="Ouverture chatbot conversationnelle typique",
        suggestion="Supprimer entièrement la formule d'appel"
    ),
    FrenchAIPattern(
        id="FR-P0-29",
        level="P0",
        category="Clôture générique",
        pattern=r"(?i)\b(?:l'avenir\s+s'annonce\s+prometteur|seul\s+le\s+temps\s+nous\s+le\s+dira|une\s+nouvelle\s+ère\s+s'ouvre|des\s+temps\s+passionnants\s+nous\s+attendent)\b",
        message="Formule de clôture générique IA creuse",
        suggestion="Remplacer par une pensée conclusive concrète ou supprimer"
    ),
    FrenchAIPattern(
        id="FR-P0-30",
        level="P0",
        category="Ouverture de résumé",
        pattern=r"(?i)\b(?:en\s+conclusion,\s+il\s+convient\s+de|il\s+ressort\s+de\s+cette\s+analyse\s+que|pour\s+résumer\b|en\s+somme\b|il\s+y\s+a\s+lieu\s+de\s+noter\s+que)\b",
        message="Ouverture de résumé IA formulaïque",
        suggestion="Aller droit au fait ou supprimer"
    ),
    FrenchAIPattern(
        id="FR-P0-34",
        level="P0",
        category="Ton sycophante",
        pattern=r"(?i)\b(?:excellente\s+question|vous\s+avez\s+tout\s+à\s+fait\s+raison|c'est\s+un\s+sujet\s+vraiment\s+important|merci\s+pour\s+cette\s+question\s+stimulante)\b\s*!?",
        message="Ton sycophante ou flatterie IA",
        suggestion="Supprimer entièrement la formule"
    ),
    FrenchAIPattern(
        id="FR-P0-44",
        level="P0",
        category="Hashtag-stuffing",
        pattern=r"(?:#\w+\s*){4,}",
        message="Accumulation de hashtags génériques IA",
        suggestion="Supprimer ou limiter à 1-2 hashtags spécifiques"
    ),

    # -------------------------------------------------------------------------
    # P1 — FORTE ODEUR IA / COLLOCATIONS CLICHÉES / HARD BLOCKERS (TOLÉRANCE 0)
    # -------------------------------------------------------------------------
    FrenchAIPattern(
        id="FR-P1-01",
        level="P1",
        category="Inflation de sens",
        pattern=r"(?i)\b(?:un\s+tournant\s+décisif|une?\s+étape\s+charnière|un\s+moment\s+historique|révolutionner\s+le\s+secteur|bouleverser\s+les\s+codes|changer\s+la\s+donne)\b",
        message="Inflation de sens / qualification historique non étayée",
        suggestion="Énoncer le fait mesurable sans qualification grandiose"
    ),
    FrenchAIPattern(
        id="FR-P1-02",
        level="P1",
        category="Apparat bibliographique vague",
        pattern=r"(?i)\b(?:selon\s+plusieurs\s+experts|de\s+nombreuses\s+études\s+récentes|la\s+communauté\s+scientifique\s+s'accorde|des\s+recherches\s+approfondies\s+montrent)\b",
        message="Apparat bibliographique vague comme geste de crédibilité",
        suggestion="Citer la source précise avec auteur et année ou supprimer"
    ),
    FrenchAIPattern(
        id="FR-P1-03",
        level="P1",
        category="Syntagme participial vide",
        pattern=r"(?i)\b(?:illustrant\s+ainsi|reflétant\s+ainsi|soulignant\s+l'importance|témoignant\s+d(?:e|'un|'une)|ouvrant\s+la\s+voie\s+à)\b",
        message="Syntagme participial creux sans contenu factuel",
        suggestion="Remplacer par un fait concret ou supprimer"
    ),
    FrenchAIPattern(
        id="FR-P1-04",
        level="P1",
        category="Vocabulaire publicitaire",
        pattern=r"(?i)\b(?:écosystème\s+innovant|solution\s+disruptive|rupture\s+technologique|synergie\s+harmonieuse)\b",
        message="Vocabulaire promotionnel / buzzword IA",
        suggestion="Décrire concrètement le fonctionnement"
    ),
    FrenchAIPattern(
        id="FR-P1-05",
        level="P1",
        category="Sources vagues",
        pattern=r"(?i)\b(?:des\s+études\s+montrent\s+que|les\s+experts\s+s'accordent\s+à\s+dire|il\s+est\s+généralement\s+admis\s+que|on\s+constate\s+souvent\s+que)\b",
        message="Attribution floue sans source vérifiable",
        suggestion="Nommer l'étude exacte ou énoncer le fait directement"
    ),
    FrenchAIPattern(
        id="FR-P1-06",
        level="P1",
        category="Défis formulaïques",
        pattern=r"(?i)\b(?:malgré\s+les\s+défis|face\s+à\s+ces\s+défis|relever\s+ces\s+défis)\b",
        message="Formulation de 'défis' abstraits sans substance",
        suggestion="Nommer le problème concret et l'action engagée"
    ),

    # Collocations clichées multi-mots (Hard Blockers stricts P1)
    # Famille essentiel : Adjectif courant en français ; seules les collocations d'emphase ('rôle essentiel') sont des tics IA avérés.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-ESSENTIEL",
        level="P1",
        category="Collocation d'emphase",
        pattern=r"(?i)\b(?:rôle|élément|dimension|composante)\s+essentiel(?:le|s|les)?\b",
        message="Collocation clichée d'emphase : 'rôle essentiel'",
        suggestion="Nommer la fonction exacte ou décrire l'effet concret"
    ),
    # Famille crucial : L'adjectif isolé est légitime en français soigné ; les associations emphatiques ('rôle crucial') trahissent l'amplification artificielle.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-CRUCIAL",
        level="P1",
        category="Collocation d'emphase",
        pattern=r"(?i)\b(?:rôle|enjeu|étape|moment)\s+crucial(?:e|s|es)?\b",
        message="Collocation clichée d'emphase : 'rôle crucial'",
        suggestion="Remplacer par 'décisif' ou quantifier avec une métrique"
    ),
    # Famille fondamental : Mot du lexique de base ; seules les formules d'autorité grandiloquente relèvent du cliché LLM.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-FONDAMENTAL",
        level="P1",
        category="Collocation d'emphase",
        pattern=r"(?i)\b(?:rôle|principe|pilier)\s+fondamental(?:e|s|es)?\b",
        message="Collocation clichée d'emphase : 'principe fondamental'",
        suggestion="Exposer la règle concrète sans superlatif"
    ),
    # Famille dynamique : Substantif/adjectif fonctionnel ; son emploi métaphorique en formule creuse ('dynamique vertueuse') est le marqueur IA.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-DYNAMIQUE",
        level="P1",
        category="Collocation clichée",
        pattern=r"(?i)\b(?:dynamique\s+(?:vertueuse|positive|collective)|s'inscri(?:t|re)\s+dans\s+une\s+dynamique)\b",
        message="Collocation clichée : 'dynamique vertueuse'",
        suggestion="Décrire l'action collective ou les résultats concrets"
    ),
    # Famille harmonie : Mots courants en fiction et description ; seule la formule convenue ('synergie harmonieuse') constitue un artefact LLM.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-HARMONIE",
        level="P1",
        category="Collocation clichée",
        pattern=r"(?i)\b(?:synergie\s+harmonieuse|équilibre\s+harmonieux|vivre\s+en\s+(?:parfaite\s+)?harmonie)\b",
        message="Collocation clichée d'accord factice : 'synergie harmonieuse'",
        suggestion="Décrire la coordination réelle ou l'agencement"
    ),
    # Famille innovation : Terme technique descriptif ; les associations marketing ('écosystème innovant') forment le cliché promotionnel IA.
    FrenchAIPattern(
        id="FR-P1-08-COLLOC-INNOVATION",
        level="P1",
        category="Collocation promotionnelle",
        pattern=r"(?i)\b(?:écosystème\s+innovant|solution\s+innovante|technologie\s+innovante|approche\s+innovante|pionnier\s+de\s+l'innovation)\b",
        message="Collocation promotionnelle : 'écosystème innovant'",
        suggestion="Préciser concrètement la nouveauté technique ou fonctionnelle"
    ),

    # Métaphores spatiales et calques IA Tier 1
    FrenchAIPattern(
        id="FR-P1-08-T1-COEUR_DE",
        level="P1",
        category="Métaphore spatiale",
        pattern=r"(?i)\bau\s+cœur\s+d(?:e|'un|'une|es)\b",
        message="Métaphore spatiale Tier 1 surutilisée",
        suggestion="Remplacer par 'dans', 'au centre de' ou expliciter le rôle"
    ),
    FrenchAIPattern(
        id="FR-P1-08-T1-NAVIGUER",
        level="P1",
        category="Calque métaphorique",
        pattern=r"(?i)\bnaviguer\s+(?:avec\s+agilité|dans\s+cet?\s+écosystème|à\s+travers)\b",
        message="Calque métaphorique anglais ('navigate') surreprésenté",
        suggestion="Remplacer par 'gérer', 'traverser' ou verbe direct"
    ),
    # Extensions narratives et fiction (Harpy & JDR)
    FrenchAIPattern(
        id="FR-P1-08-T1-TAPISSERIE",
        level="P1",
        category="Vocabulaire Tier 1 Narratif",
        pattern=r"(?i)\btapisserie\s+d(?:e|'un|'une|es)\b",
        message="Métaphore narrative IA cliché ('tapestry of')",
        suggestion="Décrire la complexité réelle sans métaphore creuse"
    ),
    FrenchAIPattern(
        id="FR-P1-08-T1-PLONGEZ_COEUR",
        level="P1",
        category="Vocabulaire Tier 1 Narratif",
        pattern=r"(?i)\bplonge(?:z|ons)\s+au\s+cœur\b",
        message="Accroche sensationnaliste promotionnelle IA",
        suggestion="Entrer directement dans l'action ou la description"
    ),
    FrenchAIPattern(
        id="FR-P1-08-T1-TOURBILLON",
        level="P1",
        category="Vocabulaire Tier 1 Narratif",
        pattern=r"(?i)\btourbillon\s+d(?:e|'un|'une|es)\b",
        message="Formule narrative sensationnaliste IA",
        suggestion="Nommer l'agitation ou l'événement précis"
    ),

    # Structures syntaxiques et transitions P1
    FrenchAIPattern(
        id="FR-P1-09",
        level="P1",
        category="Évitement de la copule",
        pattern=r"(?i)\b(?:s'inscri(?:t|vent)\s+dans\s+une?\s+(?:démarche|logique|dynamique)|se\s+tradui(?:t|sent)\s+par|s'articul(?:e|ent)\s+autour\s+de)\b",
        message="Évitement de la copule 'être' / 'avoir'",
        suggestion="Utiliser un verbe direct d'action ou être/avoir"
    ),
    FrenchAIPattern(
        id="FR-P1-12",
        level="P1",
        category="Transition mécanique",
        pattern=r"(?i)\b(?:de\s+surcroît|en\s+outre|force\s+est\s+de\s+constater|il\s+est\s+indéniable\s+que|il\s+va\s+sans\s+dire|incontestablement|indéniablement|intrinsèquement|crucialement)\b",
        message="Connecteur mécanique ou adverbe creux de transition",
        suggestion="Aller droit au fait ou supprimer la formule"
    ),
    FrenchAIPattern(
        id="FR-P1-15",
        level="P1",
        category="Accumulation de hedges",
        pattern=r"(?i)\b(?:pourrait\s+éventuellement|semble\s+potentiellement|pourrait\s+peut-être)\b",
        message="Accumulation excessive de modalisateurs (double hedge)",
        suggestion="Conserver une seule modalité ou formuler directement"
    ),
    FrenchAIPattern(
        id="FR-P1-17",
        level="P1",
        category="Faux contraste",
        pattern=r"(?i)\bsi\s+.{3,35}\s+présente\s+des\s+limites,\s+il\s+reste\b",
        message="Faux contraste rhétorique IA",
        suggestion="Nommer le compromis réel concrètement"
    ),
    # Motif #18 de SKILL-FR.md : Formatage excessif par tiret cadratin em-dash
    FrenchAIPattern(
        id="FR-P1-18",
        level="P1",
        category="Formatage excessif",
        pattern=r"—",
        message="Tiret cadratin '—' (em-dash) typique des calques LLM",
        suggestion="Remplacer par une virgule, deux-points ou des parenthèses"
    ),
    FrenchAIPattern(
        id="FR-P1-23",
        level="P1",
        category="Fausse concession",
        pattern=r"(?i)\bbien\s+que\s+.{3,35}\s+présente\s+des\s+contraintes,\s+il\s+reste\b",
        message="Fausse concession formulaïque",
        suggestion="Exposer le compromis sans formule convenue"
    ),
    FrenchAIPattern(
        id="FR-P1-24",
        level="P1",
        category="Ouverture rhétorique question",
        pattern=r"(?i)(?:^|\n)\s*(?:et\s+si\s+.{5,50}\s*\?|comment\s+réinventer\s+.{5,50}\s*\?)",
        message="Ouverture rhétorique par question stéréotypée",
        suggestion="Commencer directement par la thèse ou le fait"
    ),
    FrenchAIPattern(
        id="FR-P1-27",
        level="P1",
        category="Construction plongée",
        pattern=r"(?i)\b(?:plongeons\s+dans|explorons\s+ensemble|regardons\s+de\s+plus\s+près|parcourons\s+ensemble)\b",
        message="Construction d'invitation 'plongée' IA",
        suggestion="Aller directement au sujet sans mise en scène"
    ),
    FrenchAIPattern(
        id="FR-P1-28",
        level="P1",
        category="Disclaimer de lacune",
        pattern=r"(?i)\b(?:à\s+ma\s+connaissance|selon\s+les\s+informations\s+dont\s+je\s+dispose|à\s+la\s+date\s+de\s+mes\s+connaissances)\b",
        message="Disclaimer de coupure cognitive typique de LLM",
        suggestion="Vérifier la source ou supprimer l'assertion"
    ),
    FrenchAIPattern(
        id="FR-P1-31",
        level="P1",
        category="Marqueur d'emphase",
        pattern=r"(?i)\b(?:il\s+est\s+(?:important|crucial|essentiel|à\s+noter)\s+de\s+(?:noter|souligner)\s+que|notons\s+que|il\s+convient\s+de\s+(?:noter|souligner)\s+que|il\s+est\s+intéressant\s+de\s+constater\s+que|il\s+faut\s+souligner\s+que)\b",
        message="Marqueur d'emphase artificiel IA",
        suggestion="Supprimer la formule d'appel et énoncer le fait directement"
    ),
    FrenchAIPattern(
        id="FR-P1-33",
        level="P1",
        category="Processus de pensée",
        pattern=r"(?i)\b(?:regardons\s+cela\s+étape\s+par\s+étape|laissez-moi\s+décomposer|dans\s+l'ordre\s*:)\b",
        message="Artefact de décomposition procédurale IA",
        suggestion="Donner directement le résultat puis les points clés"
    ),
    FrenchAIPattern(
        id="FR-P1-35",
        level="P1",
        category="Boucle de confirmation",
        pattern=r"(?i)\b(?:vous\s+me\s+demandez|pour\s+répondre\s+à\s+votre\s+question|c'est\s+une\s+question\s+intéressante\s+parce\s+que)\b",
        message="Boucle de reformulation de la question",
        suggestion="Répondre directement sans commenter la question"
    ),
    # Motif #36 de SKILL-FR.md : Surstructuration avec sous-titres génériques
    FrenchAIPattern(
        id="FR-P1-36",
        level="P1",
        category="Surstructuration",
        pattern=r"(?im)^#{1,4}\s*(?:Aperçu|Points\s+clés|En\s+bref|Synthèse\s+rapide|Ce\s+qu'il\s+faut\s+retenir)\s*:",
        message="Surstructuration formulaïque avec sous-titres génériques LLM",
        suggestion="Remplacer par des titres informatifs spécifiques ou intégrer en prose continue"
    ),
    FrenchAIPattern(
        id="FR-P1-40",
        level="P1",
        category="Formule Tier 3 formulaïque",
        pattern=r"(?i)\b(?:dans\s+le\s+paysage\s+actuel\s+de|à\s+l'ère\s+d(?:e|'un|'une)|à\s+l'heure\s+où\s+les|dans\s+un\s+monde\s+qui\s+évolue\s+à\s+un\s+rythme\s+effréné|transformation\s+(?:numérique|digitale))\b",
        message="Ouverture ou expression d'époque formulaïque IA",
        suggestion="Remplacer par un contexte précis et daté"
    ),
    FrenchAIPattern(
        id="FR-P1-41",
        level="P1",
        category="Clôture prospective",
        pattern=r"(?i)\b(?:pourrait\s+devenir\s+l'un\s+des\s+enjeux\s+majeurs|sera\s+sans\s+doute\s+l'avenir\s+de)\b",
        message="Clôture prospective vague",
        suggestion="Formuler une prédiction chiffrée ou supprimer"
    ),
    # Motif #42 de SKILL-FR.md : Substantifs managériaux abstraits en liste
    FrenchAIPattern(
        id="FR-P1-42",
        level="P1",
        category="Substantifs managériaux en liste",
        pattern=r"(?im)^\s*[-*•]\s*(?:Transformation\s+(?:numérique|digitale)|Enjeux\s+stratégiques|Vision\s+globale|Excellence\s+opérationnelle|Synergie\s+(?:d'équipe|collective)|Leviers\s+de\s+croissance)\b",
        message="Liste de substantifs managériaux abstraits sans verbe ni donnée factuelle",
        suggestion="Rédiger en phrases complètes avec verbes conjugués et métriques concrètes"
    ),
    FrenchAIPattern(
        id="FR-P1-43",
        level="P1",
        category="Langue de bois managériale",
        pattern=r"(?i)\b(?:mise\s+en\s+œuvre\s+d'une\s+approche\s+globale|dans\s+une\s+logique\s+de\s+performance|démarche\s+qualité|leviers\s+de\s+performance|atout\s+différenciateur)\b",
        message="Langue de bois managériale abstraite",
        suggestion="Nommer l'action concrète ou la métrique visée"
    ),
    # Motif #45 : Seules les formules d'esquive lourdes restent bloquantes. 'il apparaît que' est rétrogradé en P2.
    FrenchAIPattern(
        id="FR-P1-45",
        level="P1",
        category="Distanciation impersonnelle",
        pattern=r"(?i)\b(?:il\s+s'avère\s+que|il\s+semblerait\s+que|force\s+est\s+de\s+constater\s+que)\b",
        message="Formule impersonnelle de distanciation lourde",
        suggestion="Utiliser une formulation active et directe"
    ),

    # -------------------------------------------------------------------------
    # P2 — RÉVISION STYLISTIQUE / SOFT WARNINGS
    # -------------------------------------------------------------------------
    FrenchAIPattern(
        id="FR-P2-07",
        level="P2",
        category="Inflation de nouveauté",
        pattern=r"(?i)\b(?:un\s+concept\s+que\s+je\s+n'avais\s+encore\s+jamais\s+rencontré|une\s+approche\s+sans\s+précédent)\b",
        message="Emphase subjective sur la nouveauté",
        suggestion="Exposer le fonctionnement sans superlatif"
    ),
    FrenchAIPattern(
        id="FR-P2-13",
        level="P2",
        category="Fausse amplitude",
        pattern=r"(?i)\b(?:de\s+la\s+recherche\s+fondamentale\s+à\s+la\s+mise\s+sur\s+le\s+marché|du\s+concept\s+à\s+la\s+réalité)\b",
        message="Formule d'amplitude stéréotypée 'de X à Y'",
        suggestion="Nommer les étapes réelles"
    ),
    # Motif #14 de SKILL-FR.md : Parenthèses rhétoriques d'exemplification
    FrenchAIPattern(
        id="FR-P2-14",
        level="P2",
        category="Parenthèse rhétorique",
        pattern=r"\((?:comme|telle?s?\s+que|notamment|par\s+exemple)\s+[^)]+\)",
        message="Parenthèse rhétorique d'exemplification affaiblissant l'affirmation",
        suggestion="Nommer directement l'exemple dans la phrase ou supprimer la parenthèse"
    ),
    FrenchAIPattern(
        id="FR-P2-15A",
        level="P2",
        category="Conditionnel-hedge",
        pattern=r"(?i)\b(?:pourrait\s+permettre\s+de|il\s+serait\s+intéressant\s+de\s+noter)\b",
        message="Hedging artificiel au conditionnel",
        suggestion="Employer l'indicatif ou supprimer la formule"
    ),
    FrenchAIPattern(
        id="FR-P2-16",
        level="P2",
        category="Adverbe en tête de phrase",
        pattern=r"(?i)(?:^|[.\n])\s*(?:Fondamentalement|En\s+substance|Globalement)\s*,",
        message="Adverbe-hedge en amorce de phrase",
        suggestion="Supprimer l'adverbe et attaquer directement"
    ),
    # Motif #21 de SKILL-FR.md : Title Case dans les titres français
    FrenchAIPattern(
        id="FR-P2-21",
        level="P2",
        category="Title Case",
        pattern=r"(?m)^#{1,4}[ \t]+[A-ZÀ-ÖØ-ß][a-zà-öø-ÿ]+(?:[ \t]+[A-ZÀ-ÖØ-ß][a-zà-öø-ÿ]+){2,}[ \t]*$",
        message="Title Case à l'anglaise dans un titre français",
        suggestion="Utiliser la typographie française (majuscule au premier mot uniquement)"
    ),
    FrenchAIPattern(
        id="FR-P2-22",
        level="P2",
        category="Inflation de listes",
        pattern=r"(?i)\bvoici\s+\d+\s+raisons\s+pour\s+lesquelles\b",
        message="Formule d'amorce d'article-liste",
        suggestion="Passer en prose ou synthétiser les points clés"
    ),
    # Motif #25 de SKILL-FR.md : Trilogie systématique artificielle
    FrenchAIPattern(
        id="FR-P2-25",
        level="P2",
        category="Trilogie systématique",
        pattern=r"(?i)\b(?:les?\s+3\s+(?:piliers|leviers|étapes|conseils|raisons|axes)|en\s+3\s+(?:points|étapes))\b",
        message="Trilogie systématique artificielle (motif des 3 piliers/étapes IA)",
        suggestion="Justifier le nombre d'éléments par le fond réel sans forcer une triade"
    ),
    FrenchAIPattern(
        id="FR-P2-32",
        level="P2",
        category="Ton émotionnel plat",
        pattern=r"(?i)\b(?:ce\s+qui\s+m'a\s+le\s+plus\s+frappé|j'ai\s+été\s+fasciné\s+de\s+découvrir)\b",
        message="Mise en scène émotionnelle simulée",
        suggestion="Présenter le fait sans feindre l'étonnement"
    ),
]

# ============================================================================
# 2. VOCABULAIRE ET TOURNURES TIER 2 / AVERTISSEMENTS RÉPÉTÉS (FRÉQUENCE >= 2)
# ============================================================================

# Règle d'or : Les termes isolés ci-dessous sont légitimes en français.
# Ils ne sont signalés en Soft Warning (P2) qu'en cas de répétition excessive (fréquence >= 2).
FRENCH_TIER2_PATTERNS: List[Tuple[str, str, str]] = [
    # Famille crucial : L'adjectif isolé est légitime en français soigné ; suspect seulement en cas de répétition.
    ("CRUCIAL", r"(?i)\bcrucial(?:e|s|es)?\b", "fournir une métrique ou un qualificatif précis"),
    # Famille essentiel : Adjectif courant du français ; suspect seulement si répété mécaniquement.
    ("ESSENTIEL", r"(?i)\bessentiel(?:le|s|les)?\b", "remplacer par 'nécessaire' ou reformuler"),
    # Famille fondamental : Mot du lexique de base ; suspect en cas d'accumulation insistante.
    ("FONDAMENTAL", r"(?i)\bfondamental(?:e|s|es)?\b", "préciser le point central concrètement"),
    # Famille dynamique : Substantif/adjectif fonctionnel ; suspect seulement si répété hors description technique.
    ("DYNAMIQUE", r"(?i)\bdynamique(?:s)?\b", "décrire l'activité ou le fonctionnement réel"),
    # Famille harmonie : Mots courants en fiction et description ; suspects en cas de répétition artificielle.
    ("HARMONIE", r"(?i)\bharmonie(?:s|ux|use|uses)?\b", "décrire l'agencement ou la coordination réelle"),
    # Famille innovation : Terme technique descriptif ; suspect en cas de matraquage marketing répété.
    ("INNOVATION", r"(?i)\b(?:innovant(?:e|s|es)?|innovation(?:s)?)\b", "décrire concrètement la nouveauté technique"),
    # Famille distanciation douce : Formule courante de nuance ; suspecte seulement en cas de répétition.
    ("IL_APPARAIT_QUE", r"(?i)\bil\s+apparaît\s+que\b", "utiliser une formulation active et directe"),
    # Familles d'adjectifs affectifs / descriptifs
    ("CAPTIVANT", r"(?i)\bcaptivant(?:e|s|es)?\b", "décrire concrètement l'intérêt ou le fait"),
    ("FASCINANT", r"(?i)\bfascinant(?:e|s|es)?\b", "décrire concrètement ce qui retient l'attention"),
    ("TROUBLANT", r"(?i)\btroublant(?:e|s|es)?\b", "nommer l'incohérence ou la surprise précise"),
    ("VERDOYANT", r"(?i)\bverdoyant(?:e|s|es)?\b", "réserver aux descriptions botaniques réelles"),
    ("REINVENTE", r"(?i)\bréinvent(?:er|é|ée|és|ées)\b", "remplacer par 'transformé', 'modifié' ou action concrète"),
    # Vocabulaire Tier 2 classique de SKILL-FR.md
    ("NOTAMMENT", r"(?i)\bnotamment\b", "en particulier, ou citer des exemples précis"),
    ("PARTICULIEREMENT", r"(?i)\bparticulièrement\b", "très, surtout, ou supprimer si vide"),
    ("ESSENTIELLEMENT", r"(?i)\bessentiellement\b", "principalement, avant tout"),
    ("DORENAVANT", r"(?i)\bdorénavant\b", "désormais, ou date précise"),
    ("CEPENDANT", r"(?i)\bcependant\b", "mais, pourtant, or"),
    ("PERMETTRE_DE", r"(?i)\bpermettre\s+de\b", "utiliser le verbe d'action direct"),
    ("METTRE_EN_LUMIERE", r"(?i)\bmettre\s+en\s+lumière\b", "montrer, révéler, signaler"),
    ("CONTRIBUER_A", r"(?i)\bcontribuer\s+à\b", "aider, renforcer, ou verbe direct"),
    ("CONSTITUER", r"(?i)\bconstituer\b", "être, former, représenter"),
    ("METTRE_EN_OEUVRE", r"(?i)\bmettre\s+en\s+œuvre\b", "appliquer, lancer, réaliser"),
    ("UNE_MULTITUDE_DE", r"(?i)\bune\s+multitude\s+de\b", "beaucoup de, ou nombre concret"),
    ("UN_LARGE_EVENTAIL_DE", r"(?i)\bun\s+large\s+éventail\s+de\b", "divers, plusieurs, ou énumérer"),
    ("EFFICACEMENT", r"(?i)\befficacement\b", "supprimer ou donner une métrique"),
    ("TRANSPARENT", r"(?i)\btransparent(?:e|s|es)?\b", "ouvert, accessible, ou préciser ce qui est consultable"),
]


# ============================================================================
# 3. MOTEUR DE SCAN DÉTERMINISTE FRANÇAIS
# ============================================================================

def scan_french_ai_patterns(
    text: str,
    allowed_terms: Optional[Set[str]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Exécute l'analyse déterministe complète sur du texte français.
    Retourne (hard_blockers, soft_warnings).
    """
    hard_blockers: List[Dict[str, Any]] = []
    soft_warnings: List[Dict[str, Any]] = []
    allowed = {t.lower() for t in (allowed_terms or set())}

    if not text or not text.strip():
        return hard_blockers, soft_warnings

    # 1. Vérification des motifs de règles de SKILL-FR.md
    for rule in FRENCH_AI_PATTERNS:
        for match in re.finditer(rule.pattern, text):
            term = match.group(0).strip()
            if term.lower() in allowed:
                continue
            line_num = text[:match.start()].count("\n") + 1
            issue = {
                "id": rule.id,
                "type": f"Hard Blocker ({rule.category})" if rule.level in ("P0", "P1") else f"Soft Warning ({rule.category})",
                "line": line_num,
                "term": term,
                "suggestion": rule.suggestion,
                "level": rule.level
            }
            if rule.level in ("P0", "P1"):
                hard_blockers.append(issue)
            else:
                soft_warnings.append(issue)

    # 2. Vérification du vocabulaire Tier 2 et expressions douces (Soft Warning si fréquence >= 2)
    for term_id, pat, suggestion in FRENCH_TIER2_PATTERNS:
        matches = [m for m in re.finditer(pat, text) if m.group(0).lower() not in allowed]
        if len(matches) >= 2:
            for m in matches:
                line_num = text[:m.start()].count("\n") + 1
                soft_warnings.append({
                    "id": f"FR-P2-T2-{term_id}",
                    "type": f"Soft Warning (Vocabulaire Tier 2 répétitif : '{m.group(0)}')",
                    "line": line_num,
                    "term": m.group(0),
                    "suggestion": suggestion,
                    "level": "P2"
                })

    return hard_blockers, soft_warnings
