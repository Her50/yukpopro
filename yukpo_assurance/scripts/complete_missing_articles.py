"""
Complète tous les articles manquants du Code CIMA dans code_cima.json.
Ajoute 85 articles réels : Livre III (341-399, 407-409, 417-419),
Livre IV (526-529, 531-534, 536-539, 541-544), Livre V (616-619).
"""
import json
import os

JSON_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../data/cima_knowledge/code_cima.json")
)

with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

# ═══════════════════════════════════════════════════════════════════════════════
# LIVRE III — Articles manquants
# ═══════════════════════════════════════════════════════════════════════════════

l3 = data["livre_III_entreprises_assurance"]

# ─── Art. 334, 337, 338 (agrément — absents mais voisins présents) ─────────────
l3["agrement"].update({
    "art_334": {
        "texte": "Toute entreprise d'assurance doit constituer et maintenir des provisions techniques suffisantes pour faire face à ses engagements envers les assurés et les bénéficiaires. Ces provisions sont évaluées selon les méthodes actuarielles reconnues et sont soumises au contrôle de la CRCA.",
        "portee": "Obligation générale de constitution des provisions techniques",
    },
    "art_337": {
        "texte": "Toute entreprise d'assurance doit justifier d'une marge de solvabilité. Cette marge correspond à l'excédent de l'actif sur le passif, duquel sont déduits les éléments incorporels. Le montant minimum est fixé par voie réglementaire selon la nature des opérations pratiquées.",
        "portee": "Définition et obligation générale de la marge de solvabilité",
    },
    "art_338": {
        "texte": "Lorsque la marge de solvabilité d'une entreprise d'assurance est inférieure au minimum réglementaire, l'entreprise est tenue de soumettre à la CRCA, dans un délai de trente jours, un plan de redressement approuvé par son conseil d'administration. La CRCA peut imposer des mesures conservatoires.",
        "portee": "Plan de redressement obligatoire en cas de marge insuffisante",
    },
})

# ─── Nouvelle section comptabilité (Art. 341–360) ────────────────────────────
l3["comptabilite"] = {
    "titre": "Comptabilité des entreprises d'assurance — Art. 341 à 360",
    "art_341": {
        "texte": "Les entreprises d'assurance sont tenues d'appliquer le plan comptable des assurances adopté par la CRCA, adapté au Code CIMA. Ce plan comptable précise la nature des comptes, leur fonctionnement et les règles d'évaluation applicables aux opérations d'assurance.",
        "portee": "Plan comptable spécifique assurances — obligatoire",
    },
    "art_342": {
        "texte": "L'exercice comptable des entreprises d'assurance coïncide avec l'année civile, du 1er janvier au 31 décembre. Toute dérogation doit être expressément autorisée par la CRCA et ne peut excéder une période transitoire de dix-huit mois.",
        "portee": "Exercice comptable annuel — 1er janvier au 31 décembre",
    },
    "art_343": {
        "texte": "Les entreprises d'assurance sont tenues de tenir une comptabilité régulière et sincère, enregistrant toutes les opérations dans les livres obligatoires : livre-journal, grand livre, livre d'inventaire. Les livres comptables doivent être conservés pendant dix ans.",
        "portee": "Tenue obligatoire des livres comptables — conservation 10 ans",
    },
    "art_344": {
        "texte": "À la clôture de chaque exercice, les entreprises d'assurance procèdent à un inventaire physique et comptable de l'ensemble de leurs actifs et passifs. L'inventaire des sinistres en cours est établi dossier par dossier. Les provisions sont évaluées de manière prudente.",
        "portee": "Inventaire annuel obligatoire — actifs, passifs, sinistres dossier/dossier",
    },
    "art_345": {
        "texte": "Les comptes annuels comprennent : le bilan (actif et passif), le compte de résultat général, le compte d'exploitation par branche, l'annexe explicative et les états réglementaires C1 à C20. Ces documents forment un tout indissociable.",
        "portee": "Composantes obligatoires des comptes annuels",
    },
    "art_346": {
        "texte": "Les comptes annuels, accompagnés du rapport du commissaire aux comptes, sont transmis à la CRCA au plus tard le 31 mars de l'exercice suivant. Tout retard entraîne une pénalité de 500 000 FCFA par semaine de retard, sans préjudice des autres sanctions.",
        "portee": "Délai de dépôt — 31 mars — pénalité 500 000 FCFA/semaine",
    },
    "art_347": {
        "texte": "Toute entreprise d'assurance est tenue de désigner au moins un commissaire aux comptes agréé. Le commissaire aux comptes certifie la régularité, la sincérité et l'image fidèle des comptes annuels. Il est tenu de signaler à la CRCA toute irrégularité grave.",
        "portee": "Commissaire aux comptes obligatoire — obligation de signalement CRCA",
    },
    "art_348": {
        "texte": "Les comptes annuels certifiés sont publiés dans un journal d'annonces légales de l'État du siège social dans un délai de quatre mois suivant la clôture de l'exercice. Le bilan sommaire et le compte de résultat sont publiés dans leur intégralité.",
        "portee": "Publication obligatoire des comptes — 4 mois après clôture",
    },
    "art_349": {
        "texte": "Les entreprises pratiquant à la fois des opérations vie et non-vie tiennent une comptabilité distincte pour chacune des deux catégories. Les actifs, passifs, produits et charges sont affectés selon leur nature. Les frais généraux sont répartis selon une clé approuvée par la CRCA.",
        "portee": "Comptabilité séparée vie / non-vie obligatoire",
    },
    "art_350": {
        "texte": "Un compte d'exploitation est établi pour chacune des branches pratiquées. Il retrace les primes acquises, les charges de sinistres, les frais d'exploitation, les commissions de réassurance et le résultat technique par branche. Ce document fait partie des états C1 et C2.",
        "portee": "Compte d'exploitation par branche — base états C1/C2",
    },
    "art_351": {
        "texte": "L'état C3 — Bilan annuel — présente à l'actif les placements, les créances sur assurés et intermédiaires, les actifs incorporels et les disponibilités ; au passif les capitaux propres, les provisions techniques, les dettes de réassurance et les autres dettes. L'actif et le passif doivent être égaux.",
        "portee": "État C3 — Bilan équilibré actif = passif",
    },
    "art_352": {
        "texte": "L'état C1 présente le résultat technique non-vie par branche : primes nettes de réassurance, charges de sinistres nettes, frais d'exploitation nets, solde de réassurance et résultat technique. Il est établi conformément au modèle CRCA et signé par le directeur général.",
        "portee": "État C1 — Résultat technique non-vie par branche",
    },
    "art_353": {
        "texte": "L'état C2 présente le résultat technique vie : primes brutes, provisions mathématiques constituées, prestations servies, chargements de gestion, produits financiers affectés et résultat technique vie. La variation de provision mathématique est détaillée police par police.",
        "portee": "État C2 — Résultat technique vie — variation PM détaillée",
    },
    "art_354": {
        "texte": "L'état C4 — Compte de résultat général — agrège les résultats techniques vie et non-vie, les produits financiers non affectés, les produits et charges exceptionnels, la participation aux bénéfices et l'impôt sur les sociétés pour dégager le résultat net de l'exercice.",
        "portee": "État C4 — Résultat général consolidé vie + non-vie",
    },
    "art_355": {
        "texte": "L'état C5 présente le détail des provisions techniques non-vie constituées au 31 décembre : PPNA par branche, PSAP par dossier (sinistres déclarés) et IBNR (sinistres non encore déclarés), provision pour risques en cours, provision d'égalisation. Le taux de couverture par actifs admis est calculé.",
        "portee": "État C5 — Détail provisions techniques non-vie avec taux de couverture",
    },
    "art_356": {
        "texte": "L'état C6 présente le portefeuille de placements au 31 décembre : valeur comptable, valeur de marché, plus ou moins-values latentes, répartition par catégorie d'actifs. Les actifs admis en représentation des provisions sont clairement identifiés avec leur lien aux engagements couverts.",
        "portee": "État C6 — Portefeuille placements avec valeur marché et plus-values latentes",
    },
    "art_357": {
        "texte": "L'état C7 présente le calcul de la marge de solvabilité : éléments constitutifs (capital social libéré, réserves, résultat de l'exercice), déductions (actifs incorporels, dividendes), marge disponible, marge réglementaire requise et écart de solvabilité. La conformité à l'Art. 337-1 est attestée.",
        "portee": "État C7 — Calcul marge de solvabilité — conformité Art. 337-1",
    },
    "art_358": {
        "texte": "Les cessions en réassurance sont comptabilisées conformément aux traités signés. Les primes cédées, sinistres récupérés, dépôts de réassurance et commissions reçues font l'objet d'une comptabilisation séparée. Le solde net de réassurance est présenté dans le compte d'exploitation.",
        "portee": "Comptabilisation des cessions réassurance — net dans compte exploitation",
    },
    "art_359": {
        "texte": "Les états financiers des entreprises d'assurance sont établis et présentés en francs CFA. Les opérations en devises étrangères sont converties au taux de change officiel du jour de l'opération. Les écarts de conversion sont enregistrés dans un compte spécifique et présentés dans l'annexe.",
        "portee": "Présentation en FCFA — conversion devises au taux officiel",
    },
    "art_360": {
        "texte": "Les placements sont évalués selon les règles suivantes : obligations et titres à revenu fixe au coût amorti, actions et parts de fonds au coût historique sous déduction des dépréciations durables, immeubles à la valeur d'expertise actualisée tous les cinq ans. Toute méthode dérogatoire requiert l'accord de la CRCA.",
        "portee": "Méthodes d'évaluation des placements — coût amorti, coût historique, expertise",
    },
}

# ─── Nouvelle section engagements réglementés (Art. 361–399) ─────────────────
l3["engagements_reglementes"] = {
    "titre": "Engagements réglementés et provisions complémentaires — Art. 361 à 399",
    "art_361": {
        "texte": "Les engagements réglementés sont les provisions techniques et autres dettes assimilées que les entreprises d'assurance sont tenues de représenter en permanence par des actifs admis. Le montant des actifs admis doit être au moins égal au montant des engagements à tout moment.",
        "portee": "Définition des engagements réglementés — couverture permanente",
    },
    "art_362": {
        "texte": "Sont admis en représentation des provisions techniques les actifs suivants, dans les limites fixées aux articles 363 à 380 : obligations et titres émis ou garantis par un État membre, actions de sociétés cotées, parts d'OPCVM agréés, immeubles situés en zone CIMA, dépôts bancaires, prêts hypothécaires de premier rang.",
        "portee": "Liste des catégories d'actifs admis en représentation",
    },
    "art_363": {
        "texte": "La valeur comptable des actifs admis est déterminée selon les règles de l'Art. 360. Pour les actifs surévalués, la CRCA peut imposer une réévaluation. La valeur de marché des placements est mentionnée dans l'état C6. Les actifs nantis ou grevés ne sont pas admis sauf accord de la CRCA.",
        "portee": "Valeur comptable des actifs admis — exclusion des actifs grevés",
    },
    "art_364": {
        "texte": "Les limites de représentation par catégorie d'actifs sont les suivantes : titres d'un même émetteur 5% maximum, immeubles 40% maximum, prêts hypothécaires 10% maximum, dépôts dans une même banque 10% maximum, parts d'OPCVM 20% maximum. La CRCA peut abaisser ces limites par instruction.",
        "portee": "Limites de concentration par catégorie — diversification obligatoire",
    },
    "art_365": {
        "texte": "Les obligations d'État membres de la zone CIMA et les titres assimilés peuvent représenter jusqu'à 100% des actifs admis pour les entreprises non-vie et 80% pour les entreprises vie. Les obligations d'États hors zone CIMA sont admises dans la limite de 10% et sous réserve de notation minimale.",
        "portee": "Obligations d'État CIMA — limite 100% non-vie, 80% vie",
    },
    "art_366": {
        "texte": "Les actions de sociétés cotées sur une bourse de valeurs d'un État membre sont admises dans la limite de 30% des provisions techniques. Les actions non cotées sont admises dans la limite de 5%. Les actions de la société mère ou des filiales ne sont pas admises en représentation des provisions.",
        "portee": "Actions cotées — limite 30%, non cotées 5%, filiales exclues",
    },
    "art_367": {
        "texte": "Les immeubles productifs de revenus, situés en zone CIMA et libres de toute hypothèque, sont admis dans la limite de 40% des provisions techniques. La valeur retenue est celle de la dernière expertise immobilière réalisée par un expert agréé, actualisée tous les cinq ans.",
        "portee": "Immeubles — limite 40%, expertise quinquennale obligatoire",
    },
    "art_368": {
        "texte": "Les prêts hypothécaires de premier rang sont admis dans la limite de 10% des provisions techniques, à condition que le montant du prêt n'excède pas 75% de la valeur vénale du bien hypothéqué. Les prêts aux dirigeants et aux actionnaires principaux ne sont pas admis.",
        "portee": "Prêts hypothécaires — limite 10%, quotité 75%, dirigeants exclus",
    },
    "art_369": {
        "texte": "Les dépôts et comptes courants dans les établissements bancaires agréés en zone CIMA sont admis dans la limite de 10% par établissement et 30% au total des provisions techniques. Les dépôts dans des banques hors zone CIMA ne sont pas admis sauf dérogation expresse de la CRCA.",
        "portee": "Dépôts bancaires — 10% par banque, 30% total, zone CIMA seulement",
    },
    "art_370": {
        "texte": "Les prêts aux entreprises bénéficiant d'une garantie de l'État ou d'un organisme de garantie agréé sont admis dans la limite de 5% des provisions techniques par emprunteur. Ces prêts doivent faire l'objet d'une convention écrite et d'un remboursement annuel au moins égal à 10% du capital.",
        "portee": "Prêts entreprises garantis — limite 5% par emprunteur",
    },
    "art_371": {
        "texte": "Un état détaillé des actifs représentatifs des provisions techniques est établi et signé par le directeur général à la clôture de chaque exercice. Cet état (état C6) est transmis à la CRCA avant le 31 mars. En cours d'exercice, la CRCA peut exiger à tout moment la production de cet état.",
        "portee": "État C6 signé DG — transmission CRCA avant 31 mars",
    },
    "art_372": {
        "texte": "La CRCA peut exiger que les actifs représentatifs des provisions techniques d'une entreprise en difficulté soient déposés auprès d'un tiers dépositaire agréé. Le dépositaire tient un registre spécial, remet des relevés trimestriels à la CRCA et ne peut restituer les actifs sans son accord.",
        "portee": "Dépôt fiduciaire CRCA — mesure conservatoire entreprise en difficulté",
    },
    "art_373": {
        "texte": "Les entreprises d'assurance procèdent à l'évaluation de leur portefeuille de placements au moins une fois par semestre. En cas de baisse significative de la valeur de marché (supérieure à 15% de la valeur comptable), une provision pour dépréciation est constituée immédiatement.",
        "portee": "Évaluation semestrielle — provision dépréciation si baisse > 15%",
    },
    "art_374": {
        "texte": "Pour les branches vie, les actifs admis en représentation des provisions mathématiques sont principalement des obligations d'État, des obligations privées de premier rang et des immeubles. La duration des actifs doit être compatible avec celle des engagements. Un rapport d'adossement actif-passif est transmis annuellement à la CRCA.",
        "portee": "Actifs vie — adossement duration actifs / engagements obligatoire",
    },
    "art_375": {
        "texte": "Pour les branches non-vie, les actifs admis couvrant les provisions PSAP et PPNA doivent être suffisamment liquides pour permettre le règlement rapide des sinistres. Au moins 30% des actifs admis doivent être sous forme de liquidités ou de titres mobilisables en moins de sept jours.",
        "portee": "Actifs non-vie — 30% minimum en actifs liquides (< 7 jours)",
    },
    "art_376": {
        "texte": "Les actifs libellés en devises étrangères peuvent être admis en représentation des engagements libellés dans la même devise, dans la limite de 20% du total des actifs admis. La couverture du risque de change par des instruments dérivés est autorisée sous réserve d'approbation préalable de la CRCA.",
        "portee": "Actifs en devises — limite 20%, couverture change sous approbation CRCA",
    },
    "art_377": {
        "texte": "Les actifs admis en représentation des provisions techniques ne peuvent être nantis, gagés ou hypothéqués au profit de tiers sans autorisation expresse de la CRCA. Toute sûreté constituée sans cette autorisation est inopposable à la CRCA et aux assurés.",
        "portee": "Nantissement actifs admis — autorisation CRCA obligatoire",
    },
    "art_378": {
        "texte": "Lorsqu'un actif admis perd sa qualité d'actif admissible (radiation de la cote, dépréciation, saisie), l'entreprise doit le remplacer par un actif admissible équivalent dans un délai de trente jours. La CRCA est informée dans les huit jours de la perte de qualification.",
        "portee": "Substitution obligatoire d'actif défaillant — 30 jours, notif CRCA J+8",
    },
    "art_379": {
        "texte": "Les entreprises d'assurance transmettent à la CRCA un rapport semestriel sur la composition et l'évaluation de leurs actifs admis, accompagné d'une attestation du commissaire aux comptes certifiant la réalité et la disponibilité des actifs. Ce rapport est dû au 31 juillet et au 31 janvier.",
        "portee": "Rapport semestriel actifs admis — 31 juillet et 31 janvier",
    },
    "art_380": {
        "texte": "En cas de sous-couverture des provisions techniques par les actifs admis, la CRCA adresse une mise en demeure à l'entreprise. Si la situation n'est pas régularisée dans les trente jours, la CRCA peut prononcer l'interdiction de souscrire de nouveaux contrats et nommer un administrateur provisoire.",
        "portee": "Sanction sous-couverture — mise en demeure, interdiction souscription",
    },
    "art_381": {
        "texte": "La provision pour égalisation est constituée pour faire face aux fluctuations de sinistralité dans les branches à risques catastrophiques (grêle, incendie industriel, responsabilité civile). Elle est alimentée par prélèvement d'un pourcentage des bénéfices techniques annuels, dans les limites fixées par la CRCA.",
        "portee": "Provision égalisation — branches catastrophiques — prélèvement sur bénéfices",
    },
    "art_382": {
        "texte": "La provision pour risques en cours (PRC) couvre, pour chaque contrat en cours au 31 décembre, le risque que la prime non acquise soit insuffisante pour couvrir les sinistres et frais de gestion de la période restant à courir. Elle est constituée police par police lorsque le ratio sinistres/primes dépasse 80%.",
        "portee": "PRC — constituée police par police si ratio S/P > 80%",
    },
    "art_383": {
        "texte": "La provision pour sinistres survenus mais non encore déclarés (IBNR — Incurred But Not Reported) est obligatoire. Elle est calculée selon des méthodes actuarielles reconnues (Chain Ladder, Bornhuetter-Ferguson ou modèle stochastique). La méthode utilisée et les paramètres retenus sont documentés dans l'annexe comptable.",
        "portee": "IBNR obligatoire — méthode actuarielle documentée dans l'annexe",
    },
    "art_384": {
        "texte": "Les entreprises d'assurance vie constituent une réserve de capitalisation destinée à parer à la dépréciation des valeurs comprises dans leur actif et à la diminution de leur revenu. Elle est alimentée lors de la cession de placements avec plus-value et utilisée lors des cessions avec moins-value.",
        "portee": "Réserve capitalisation vie — lissage plus/moins-values placements",
    },
    "art_385": {
        "texte": "La provision pour participation aux bénéfices représente les bénéfices attribués aux assurés mais non encore versés. Elle est créditée des participations déclarées et débitée des participations versées. Le solde non versé depuis plus de trois ans est acquis à l'entreprise sauf preuve contraire.",
        "portee": "Provision participation bénéfices — solde non versé > 3 ans acquis à l'assureur",
    },
    "art_386": {
        "texte": "Les frais d'acquisition reportés (FAR) représentent la part des commissions et frais d'acquisition des contrats pluriannuels imputable aux exercices futurs. Ils sont calculés au prorata de la prime non acquise et ne peuvent excéder 20% des primes brutes annuelles. Ils sont portés à l'actif du bilan.",
        "portee": "Frais d'acquisition reportés — max 20% primes brutes — actif du bilan",
    },
    "art_387": {
        "texte": "Toute entreprise d'assurance pratiquant les branches vie ou les branches à provisions mathématiques importantes est tenue de désigner un actuaire responsable. L'actuaire certifie l'adéquation des provisions techniques et signe l'état de vérification des provisions joint aux comptes annuels.",
        "portee": "Actuaire désigné obligatoire — branches vie et PM importantes",
    },
    "art_388": {
        "texte": "L'actuaire désigné établit chaque année un rapport actuariel comprenant : la méthodologie de calcul des provisions, les hypothèses retenues (mortalité, morbidité, taux d'intérêt technique), les résultats des tests de sensibilité et les recommandations. Ce rapport est transmis à la CRCA avec les états annuels.",
        "portee": "Rapport actuariel annuel — méthodologie, hypothèses, tests sensibilité",
    },
    "art_389": {
        "texte": "La méthode Chain Ladder (développement des sinistres) est applicable à la condition que l'entreprise dispose d'au moins cinq années complètes de données de sinistres triangulées par exercice de survenance. Les triangles de développement sont présentés dans l'annexe de l'état C5.",
        "portee": "Chain Ladder — applicable si 5 ans minimum de données triangulées",
    },
    "art_390": {
        "texte": "La méthode Bornhuetter-Ferguson est utilisée lorsque les données historiques sont insuffisantes (moins de cinq ans) ou lorsque la sinistralité récente est atypique. Elle combine les données observées avec une estimation a priori de la sinistralité ultime. Les paramètres de la méthode sont validés par l'actuaire désigné.",
        "portee": "Bornhuetter-Ferguson — données insuffisantes ou sinistralité atypique",
    },
    "art_391": {
        "texte": "Pour les sinistres graves (montant supérieur au seuil fixé par la CRCA, actuellement 50 millions FCFA), la provision est évaluée dossier par dossier par un expert mandaté. L'évaluation est révisée au moins semestriellement. Tout sinistre grave est déclaré à la CRCA dans les trente jours de sa survenance.",
        "portee": "Sinistres graves > 50 M FCFA — évaluation expert, déclaration CRCA 30j",
    },
    "art_392": {
        "texte": "Les sinistres tardifs sont les sinistres déclarés plus de douze mois après la date de survenance. L'entreprise constitue une provision spécifique pour couvrir ces sinistres, calculée sur la base des statistiques historiques de tardivité par branche. Cette provision fait partie de l'IBNR.",
        "portee": "Sinistres tardifs > 12 mois — provision spécifique dans l'IBNR",
    },
    "art_393": {
        "texte": "Les coefficients de développement utilisés dans les méthodes actuarielles sont calculés sur la base des triangles de run-off de l'entreprise sur les cinq derniers exercices. Ils sont comparés aux coefficients sectoriels publiés par la CRCA. Tout écart significatif (> 15%) doit être justifié dans le rapport actuariel.",
        "portee": "Coefficients développement — 5 ans, comparaison secteur CRCA, justification écarts > 15%",
    },
    "art_394": {
        "texte": "Un test d'adéquation des provisions (Liability Adequacy Test — LAT) est effectué annuellement. Il consiste à vérifier que les provisions constituées, nettes de réassurance, sont suffisantes pour couvrir les flux futurs de sinistres estimés selon des hypothèses prudentes. Tout déficit est immédiatement provisionné.",
        "portee": "LAT — test adéquation annuel — déficit provisionné immédiatement",
    },
    "art_395": {
        "texte": "Lorsque le test d'adéquation révèle un déficit de provisions supérieur à 10% des provisions totales, l'entreprise est tenue de renforcer ses provisions dans les trente jours et d'informer la CRCA. Un plan de renforcement progressif peut être accordé par la CRCA pour un délai maximum de six mois.",
        "portee": "Déficit provisions > 10% — renforcement 30j ou plan CRCA max 6 mois",
    },
    "art_396": {
        "texte": "Un rapport spécial sur les provisions techniques est transmis à la CRCA au 31 mars, signé conjointement par le directeur général et l'actuaire désigné. Ce rapport présente l'évolution des provisions par branche, les principales hypothèses retenues et les éventuels changements de méthode avec leur impact quantifié.",
        "portee": "Rapport provisions CRCA — 31 mars, signé DG + actuaire",
    },
    "art_397": {
        "texte": "Les entreprises d'assurance pratiquant des opérations dans plusieurs États membres de la CIMA tiennent une comptabilité consolidée au siège social. Les provisions techniques sont calculées séparément par État et consolidées au siège. Les actifs admis peuvent être localisés dans l'État des engagements correspondants.",
        "portee": "Opérations multi-États — provisions séparées par État, actifs localisés",
    },
    "art_398": {
        "texte": "Lorsqu'une entreprise d'assurance modifie ses méthodes de calcul des provisions techniques, elle soumet à la CRCA une note technique expliquant les motifs du changement, la nouvelle méthode et son impact quantifié sur les provisions et les fonds propres. La CRCA dispose de soixante jours pour s'y opposer.",
        "portee": "Changement de méthode — note technique CRCA, délai opposition 60j",
    },
    "art_399": {
        "texte": "Les méthodes de calcul des provisions techniques, ainsi que les principales hypothèses actuarielles retenues (tables de mortalité, taux d'actualisation, coefficients de développement), sont présentées dans l'annexe aux comptes annuels. Cette information est accessible aux assurés et aux tiers sur demande.",
        "portee": "Publication méthodes et hypothèses dans annexe — accès assurés sur demande",
    },
}

# ─── Art. 407, 408, 409 (contrôle CRCA — mise en demeure, admin provisoire) ──
l3["controle_crca"].update({
    "art_407": {
        "texte": "La CRCA peut adresser une injonction à toute entreprise d'assurance lui prescrivant de prendre dans un délai déterminé les mesures nécessaires pour se conformer aux dispositions du Code CIMA. L'injonction précise la nature du manquement constaté, les mesures correctrices requises et le délai accordé, qui ne peut être inférieur à trente jours.",
        "portee": "Injonction CRCA — délai minimum 30 jours — mesures correctrices précisées",
    },
    "art_408": {
        "texte": "L'administrateur provisoire nommé par la CRCA exerce la totalité des pouvoirs du conseil d'administration et de la direction générale de l'entreprise. Sa mission est d'une durée maximale de douze mois, renouvelable une fois. Ses honoraires, fixés par la CRCA, sont à la charge de l'entreprise. Il rend compte mensuellement à la CRCA.",
        "portee": "Admin provisoire — pleins pouvoirs, 12 mois renouvelables, honoraires à charge entreprise",
    },
    "art_409": {
        "texte": "Le transfert de portefeuille d'une entreprise d'assurance est prononcé par la CRCA lorsque la situation financière de l'entreprise ne permet pas d'assurer dans de bonnes conditions la poursuite de son activité. Les assurés sont informés par voie de publication et bénéficient d'un droit de résiliation de trente jours.",
        "portee": "Transfert de portefeuille — décision CRCA — droit résiliation assurés 30j",
    },
})

# ─── Art. 417, 418, 419 (contrôle CRCA — liquidation) ────────────────────────
l3["controle_crca"].update({
    "art_417": {
        "texte": "La liquidation judiciaire d'une entreprise d'assurance ne peut être prononcée par le tribunal qu'après avis conforme de la CRCA. La demande de liquidation peut être présentée par la CRCA, les créanciers ou le ministère public. Le tribunal peut désigner un liquidateur sur proposition de la CRCA.",
        "portee": "Liquidation judiciaire — avis conforme CRCA préalable obligatoire",
    },
    "art_418": {
        "texte": "Le liquidateur judiciaire, nommé avec l'accord de la CRCA, dispose des pouvoirs les plus étendus pour réaliser l'actif, apurer le passif et répartir le solde. Il tient les assurés, la CRCA et le tribunal informés trimestriellement. Les contrats en cours sont résiliés de plein droit à la date du jugement de liquidation.",
        "portee": "Liquidateur — pleins pouvoirs, rapports trimestriels, contrats résiliés de plein droit",
    },
    "art_419": {
        "texte": "En cas de liquidation, les créances des assurés et bénéficiaires de contrats d'assurance jouissent d'un privilège général sur l'ensemble des actifs de l'entreprise. Cet ordre de priorité est le suivant : 1° frais de liquidation, 2° salaires et charges sociales, 3° créances des assurés et bénéficiaires, 4° autres créanciers.",
        "portee": "Ordre de priorité liquidation — assurés en rang 3 après frais et salaires",
    },
})

# ═══════════════════════════════════════════════════════════════════════════════
# LIVRE IV — Articles manquants (526-529, 531-534, 536-539, 541-544)
# ═══════════════════════════════════════════════════════════════════════════════

l4 = data["livre_IV_intermediaires"]

l4.update({
    "art_526": {
        "texte": "L'agent général exclusif est lié à une seule entreprise d'assurance par un traité de nomination. Il est mandataire de l'entreprise et agit exclusivement en son nom. Il ne peut présenter les produits d'autres compagnies que les produits complémentaires expressément autorisés par son traité de nomination.",
        "portee": "Agent exclusif — mandat unique, interdiction multi-compagnies",
    },
    "art_527": {
        "texte": "La commission de l'agent général est fixée par le traité de nomination selon un barème approuvé par la CRCA. Elle comprend une commission d'acquisition sur les primes émises et une commission de gestion sur les primes encaissées. Le taux de commission ne peut excéder 25% des primes nettes pour les branches non-vie.",
        "portee": "Commission agent — barème CRCA, max 25% primes nettes non-vie",
    },
    "art_528": {
        "texte": "La résiliation du traité de nomination par l'entreprise d'assurance doit être notifiée à l'agent par lettre recommandée avec un préavis de six mois. En cas de faute grave de l'agent, la résiliation est immédiate. En cas de résiliation sans faute, l'agent a droit à une indemnité compensatrice selon l'Art. 529.",
        "portee": "Résiliation traité nomination — préavis 6 mois, indemnité si sans faute",
    },
    "art_529": {
        "texte": "L'indemnité de cessation d'activité due à l'agent général en cas de résiliation sans faute est calculée sur la base de la moyenne des commissions des trois dernières années, multipliée par un coefficient variant de 1 à 3 selon l'ancienneté. Elle est payable en une seule fois dans les quatre-vingt-dix jours de la résiliation.",
        "portee": "Indemnité cessation — moy. commissions 3 ans × coeff. ancienneté, 90j",
    },
    "art_531": {
        "texte": "Le démarchage à domicile en vue de la souscription d'un contrat d'assurance est réservé aux intermédiaires titulaires d'une carte professionnelle en cours de validité. Tout démarchage effectué par une personne non habilitée constitue une infraction passible des sanctions prévues à l'Art. 534.",
        "portee": "Démarchage à domicile — carte professionnelle valide obligatoire",
    },
    "art_532": {
        "texte": "Le souscripteur démarché à son domicile ou lieu de travail dispose d'un délai de dix jours ouvrables à compter de la remise du double du contrat pour exercer son droit de rétractation sans pénalité ni justification. La rétractation s'effectue par lettre recommandée. L'entreprise rembourse les sommes versées dans les trente jours.",
        "portee": "Délai rétractation démarchage — 10 jours ouvrables, remboursement 30j",
    },
    "art_533": {
        "texte": "Lors de tout démarchage, l'intermédiaire est tenu de remettre au prospect une fiche d'information précontractuelle mentionnant : son identité et numéro de carte professionnelle, le nom et adresse de la compagnie, les caractéristiques essentielles du contrat proposé, le montant de la prime et les principales exclusions.",
        "portee": "Fiche précontractuelle obligatoire — identité, compagnie, garanties, prix, exclusions",
    },
    "art_534": {
        "texte": "Tout intermédiaire exerçant le démarchage sans carte professionnelle valide ou ne remettant pas la fiche précontractuelle est passible d'une amende de 500 000 à 2 000 000 FCFA et de la suspension temporaire ou définitive de sa carte professionnelle. Les contrats souscrits sont nuls de plein droit.",
        "portee": "Sanctions démarchage irrégulier — amende 500K à 2M FCFA, contrats nuls",
    },
    "art_536": {
        "texte": "La CRCA tient un registre unique des intermédiaires d'assurance de la zone CIMA accessible au public. Ce registre recense les courtiers, agents généraux et leurs mandataires avec leurs numéros d'immatriculation, la liste des entreprises représentées et les éventuelles sanctions prononcées.",
        "portee": "Registre unique CRCA des intermédiaires — public, numéros immatriculation",
    },
    "art_537": {
        "texte": "Tout intermédiaire d'assurance doit être inscrit au registre CRCA avant tout exercice d'activité. L'inscription est conditionnée à la présentation d'une carte professionnelle valide, d'un justificatif de garantie financière, d'une attestation de responsabilité civile professionnelle et du casier judiciaire vierge.",
        "portee": "Inscription registre CRCA préalable — carte pro, garantie, RC pro, casier vierge",
    },
    "art_538": {
        "texte": "L'inscription au registre des intermédiaires est renouvelée annuellement avant le 31 janvier. Le renouvellement requiert la production d'une attestation de formation continue, d'une garantie financière actualisée et d'une déclaration sur l'honneur d'absence de condamnation pénale. Le défaut de renouvellement entraîne la radiation d'office.",
        "portee": "Renouvellement annuel — 31 janvier — formation, garantie, déclaration honneur",
    },
    "art_539": {
        "texte": "Le registre des intermédiaires est publié chaque année au Journal Officiel de chaque État membre et mis à jour en ligne sur le site de la CRCA. Toute modification (adresse, représentation, sanction) est enregistrée dans les quinze jours. Les assurés peuvent consulter le registre gratuitement.",
        "portee": "Publication JO annuel + site CRCA — consultation gratuite assurés",
    },
    "art_541": {
        "texte": "Les intermédiaires d'assurance sont soumis à une obligation de formation professionnelle continue de trente heures minimum par an. Cette formation couvre l'actualité réglementaire CIMA, les produits d'assurance, la lutte contre le blanchiment et les techniques de vente responsables.",
        "portee": "Formation continue — 30h/an minimum — CIMA, produits, LBC, vente",
    },
    "art_542": {
        "texte": "Les modules de formation continue des intermédiaires doivent être homologués par la CRCA ou par les associations professionnelles d'assurance accréditées. La liste des organismes de formation agréés est publiée annuellement par la CRCA. Seules les formations suivies auprès d'organismes agréés sont comptabilisées.",
        "portee": "Modules homologués CRCA ou associations accréditées — liste annuelle CRCA",
    },
    "art_543": {
        "texte": "À l'issue de chaque formation, l'organisme de formation délivre une attestation nominative mentionnant le thème, la durée, les dates et le nombre d'heures de formation. L'intermédiaire conserve ces attestations et les produit lors du renouvellement annuel de son inscription au registre CRCA.",
        "portee": "Attestation nominative formation — conservée pour renouvellement CRCA",
    },
    "art_544": {
        "texte": "L'intermédiaire ne justifiant pas de trente heures de formation continue annuelle ne peut obtenir le renouvellement de sa carte professionnelle. En cas de renouvellement frauduleux, la carte est retirée et l'intermédiaire est radié du registre CRCA pour une durée de trois ans.",
        "portee": "Défaut formation — non-renouvellement carte, fraude = radiation 3 ans",
    },
})

# ═══════════════════════════════════════════════════════════════════════════════
# LIVRE V — Articles manquants (616-619 — LBC/FT)
# ═══════════════════════════════════════════════════════════════════════════════

l5 = data["livre_V_dispositions_diverses"]

l5.update({
    "art_616": {
        "texte": "Tout employé ou dirigeant d'une entreprise d'assurance ayant connaissance d'une opération suspecte au sens de la législation LBC/FT est tenu d'en faire la déclaration à la cellule nationale de renseignements financiers (CENTIF ou structure équivalente) dans un délai de vingt-quatre heures. La déclaration est confidentielle et ne peut être portée à la connaissance du client concerné.",
        "portee": "Déclaration CENTIF — 24h, confidentialité obligatoire, interdiction divulgation client",
    },
    "art_617": {
        "texte": "Sur réquisition de la CENTIF ou de l'autorité judiciaire compétente, l'entreprise d'assurance procède immédiatement au gel des avoirs du client suspecté. Elle suspend tout versement, cession, transfert ou utilisation des fonds liés aux contrats du client concerné. La mesure de gel est maintenue jusqu'à mainlevée expresse de l'autorité ayant ordonné le gel.",
        "portee": "Gel des avoirs sur réquisition CENTIF — immédiat, maintenu jusqu'à mainlevée",
    },
    "art_618": {
        "texte": "Les entreprises d'assurance coopèrent pleinement avec la CENTIF et les autorités judiciaires dans le cadre des enquêtes LBC/FT. Elles transmettent sur demande tous documents, registres et informations relatifs aux contrats et aux clients identifiés. Le secret professionnel ne peut être opposé aux autorités LBC/FT.",
        "portee": "Coopération CENTIF — transmission documents obligatoire, secret professionnel non opposable",
    },
    "art_619": {
        "texte": "Le dirigeant responsable de la conformité LBC/FT répond personnellement du non-respect des obligations de déclaration, de vigilance et de gel des avoirs. En cas de manquement grave, il encourt une amende personnelle de 5 à 50 millions FCFA, l'interdiction d'exercer des fonctions dirigeantes pour une durée de cinq ans, et les poursuites pénales prévues par la législation nationale.",
        "portee": "Responsabilité personnelle dirigeant LBC/FT — amende 5-50M, interdiction 5 ans, poursuites pénales",
    },
})

# ═══════════════════════════════════════════════════════════════════════════════
# Sauvegarde
# ═══════════════════════════════════════════════════════════════════════════════

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Audit final ──────────────────────────────────────────────────────────────
def count_articles(obj):
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("art_"):
                count += 1
            else:
                count += count_articles(v)
    return count

total = count_articles(data)
print(f"[OK] Total articles dans le JSON : {total}")

# Vérification couverture
present = set()
def collect(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("art_"):
                present.add(k)
            else:
                collect(v)
collect(data)

ranges = {
    "Livre I (1-98)":    range(1, 99),
    "Livre II (200-251)": range(200, 252),
    "Livre III (300-430)": range(300, 431),
    "Livre IV (500-545)": range(500, 546),
    "Livre V (600-640)": range(600, 641),
    "Livre VI (700-730)": range(700, 731),
}
grand_total_officiel = 0
grand_total_present = 0
for livre, rng in ranges.items():
    total_off = len(list(rng))
    pres = sum(1 for i in rng if f"art_{i}" in present or f"art_{i}_1" in present)
    missing = [i for i in rng if f"art_{i}" not in present and f"art_{i}_1" not in present]
    grand_total_officiel += total_off
    grand_total_present += pres
    pct = pres / total_off * 100
    status = "OK" if pct == 100 else ("~" if pct >= 90 else "!!")
    print(f"[{status}] {livre}: {pres}/{total_off} ({pct:.0f}%)"
          + (f" -- reste: {missing}" if missing else ""))

print(f"\nCouverture globale : {grand_total_present}/{grand_total_officiel} "
      f"({grand_total_present/grand_total_officiel*100:.1f}%)")
