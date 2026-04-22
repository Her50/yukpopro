"""
Script de mise à jour du code_cima.json
Ajoute tous les articles manquants des Livres I à VI.
"""
import json, os

JSON_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '../data/cima_knowledge/code_cima.json'))

with open(JSON_PATH, encoding='utf-8') as f:
    data = json.load(f)

# ─── LIVRE I : Art. 34-49 dans chapitre_V_assurances_dommages ─────────────────

data['livre_I_contrat_assurance']['chapitre_V_assurances_dommages'].update({
    "art_34": {
        "texte": "En cas de coassurance, chaque assureur ne répond que de sa quote-part du risque. Un mandataire commun représente les coassureurs dans les relations avec l'assuré pour la gestion du contrat et le règlement des sinistres.",
        "portee": "Coassurance — responsabilité proportionnelle de chaque coassureur"
    },
    "art_35": {
        "texte": "L'assurance peut être souscrite pour le compte de qui il appartiendra. La clause vaut à la fois assurance au profit du souscripteur et assurance au profit du ou des tiers bénéficiaires désignés ou à désigner.",
        "portee": "Assurance pour le compte d'autrui"
    },
    "art_36": {
        "texte": "En cas de pluralité d'assurances couvrant le même risque, l'assuré peut demander à l'un quelconque des assureurs l'exécution du contrat. L'assureur qui a payé dispose d'un recours proportionnel contre les autres assureurs.",
        "portee": "Pluralité d'assurances — recours entre coassureurs"
    },
    "art_37": {
        "texte": "Toute assurance souscrite pour une valeur supérieure à la valeur réelle du bien assuré est réputée sur-assurance. Si la sur-assurance est frauduleuse, le contrat est nul. Si elle est de bonne foi, seule la prime correspondant à la valeur réelle est due.",
        "portee": "Sur-assurance — nullité en cas de fraude"
    },
    "art_38": {
        "texte": "Les parties peuvent convenir d'une valeur agréée (valeur convenue d'avance). En cas de perte totale, l'indemnité est égale à la valeur agréée sans application de la règle proportionnelle. En cas de perte partielle, la règle proportionnelle s'applique si sous-assurance.",
        "portee": "Valeur agréée — dispense de règle proportionnelle pour perte totale"
    },
    "art_39": {
        "texte": "L'assurance à valeur à neuf garantit le remboursement du coût de remplacement du bien sinistré à l'état neuf, sans déduction pour vétusté, dans la limite de l'âge et de l'état convenu aux conditions particulières.",
        "portee": "Assurance à valeur à neuf"
    },
    "art_40": {
        "texte": "Dans l'assurance en premier risque, l'assuré fixe un plafond d'indemnisation sans déclaration de la valeur totale du bien. L'assureur indemnise jusqu'au plafond sans appliquer la règle proportionnelle.",
        "portee": "Assurance en premier risque — pas de règle proportionnelle"
    },
    "art_41": {
        "texte": "Dans les assurances de responsabilité civile, l'assureur a l'obligation de prendre en charge la défense de l'assuré contre les réclamations des tiers, y compris de mandater un avocat à ses frais dans la limite des garanties contractuelles.",
        "portee": "Obligation de défense de l'assuré en RC"
    },
    "art_42": {
        "texte": "La garantie RC couvre les dommages corporels, matériels et immatériels consécutifs causés aux tiers du fait de l'assuré, de ses préposés et des biens qu'il a sous sa garde, dans les limites définies au contrat.",
        "portee": "Étendue de la garantie RC — corporels, matériels, immatériels"
    },
    "art_43": {
        "texte": "Sont exclus de plein droit des garanties d'assurance : les dommages causés intentionnellement par l'assuré, les amendes et pénalités pénales, les dommages causés en état d'ivresse manifeste, et les dommages résultant d'un acte de guerre déclaré.",
        "portee": "Exclusions légales d'ordre public en RC"
    },
    "art_44": {
        "texte": "L'assureur RC qui a indemnisé le tiers lésé est subrogé dans les droits de ce tiers contre le responsable non assuré ou partiellement assuré. Le recours subrogatoire ne peut être exercé contre l'assuré qu'en cas de faute intentionnelle.",
        "portee": "Subrogation de l'assureur RC — limites du recours contre l'assuré"
    },
    "art_45": {
        "texte": "L'état de catastrophe naturelle est constaté par arrêté du ministre chargé des assurances de l'État membre concerné, sur avis de la commission nationale compétente. La garantie catastrophe naturelle est obligatoire dans les contrats dommages aux biens.",
        "portee": "Catastrophes naturelles — déclaration officielle obligatoire"
    },
    "art_46": {
        "texte": "En cas d'état de catastrophe naturelle déclaré, l'assureur doit prononcer l'indemnisation dans les 3 mois suivant la remise par l'assuré de l'état estimatif des pertes. La franchise légale catastrophe naturelle est fixée par arrêté.",
        "delai_indemnisation_catnat_mois": 3,
        "portee": "Délai d'indemnisation catastrophe naturelle — 3 mois"
    },
    "art_47": {
        "texte": "Dans les assurances de protection juridique, si un conflit d'intérêt survient entre l'assureur et l'assuré, ce dernier a le droit de choisir librement son avocat aux frais de l'assureur, dans la limite du plafond contractuel.",
        "portee": "Libre choix de l'avocat en protection juridique"
    },
    "art_48": {
        "texte": "L'assureur RC peut prendre la direction du procès intenté contre l'assuré. Il ne peut transiger sans l'accord de l'assuré si le règlement impose à ce dernier une reconnaissance de responsabilité allant au-delà du contrat.",
        "portee": "Direction du procès par l'assureur RC"
    },
    "art_49": {
        "texte": "Les pertes immatérielles consécutives ne sont garanties que si elles sont expressément mentionnées aux conditions particulières. À défaut de stipulation, la garantie ne couvre que les dommages directs.",
        "portee": "Pertes immatérielles — garantie expressément stipulée"
    }
})

# ─── LIVRE I : Art. 55-72 dans chapitre_VI_assurances_personnes ───────────────

data['livre_I_contrat_assurance']['chapitre_VI_assurances_personnes'].update({
    "art_55": {
        "texte": "Après deux ans de contrat, l'assureur ne peut se prévaloir de la réticence ou de la fausse déclaration de l'assuré sauf si elle a été faite de mauvaise foi. L'incontestabilité protège l'assuré de bonne foi après 2 ans.",
        "delai_incontestabilite_ans": 2,
        "portee": "INCONTESTABILITÉ — assurance vie après 2 ans"
    },
    "art_56": {
        "texte": "Le souscripteur peut obtenir des avances sur sa police à hauteur de la valeur de rachat. Les intérêts des avances sont fixés par l'assureur et ne peuvent dépasser le taux technique majoré de 2 points. L'avance non remboursée est déduite du capital en cas de sinistre.",
        "taux_max_avance": "Taux technique + 2%",
        "portee": "Avances sur police vie"
    },
    "art_57": {
        "texte": "La police d'assurance-vie peut être mise en nantissement au profit d'un créancier. Le nantissement est notifié à l'assureur par acte authentique ou sous seing privé. L'assureur ne peut payer le bénéficiaire qu'après mainlevée du créancier nanti.",
        "portee": "Nantissement de la police vie"
    },
    "art_58": {
        "texte": "La valeur de rachat minimale garantie est calculée selon les tables publiées par la CRCA. L'assureur doit communiquer au souscripteur, à chaque anniversaire de contrat, la valeur de rachat et la valeur réduite de sa police.",
        "periodicite_information": "Annuelle (anniversaire contrat)",
        "portee": "Valeur de rachat minimale — obligation d'information annuelle"
    },
    "art_59": {
        "texte": "En cas de non-paiement de prime après mise en demeure, l'assuré peut opter pour la réduction du contrat : l'assurance se maintient sans nouvelles primes pour un capital réduit proportionnel aux primes déjà versées.",
        "portee": "Réduction de l'assurance-vie en cas de non-paiement"
    },
    "art_60": {
        "texte": "Le souscripteur désigne librement le ou les bénéficiaires. La désignation peut être nominative ou qualitative (ex. : conjoint, enfants). Elle peut être faite dans le contrat, par avenant, ou par testament.",
        "portee": "Désignation du bénéficiaire — liberté et formes"
    },
    "art_61": {
        "texte": "La désignation du bénéficiaire est librement révocable par le souscripteur, sauf acceptation formelle. La révocation est faite par avenant au contrat ou par acte authentique notifié à l'assureur.",
        "portee": "Révocation de la désignation du bénéficiaire"
    },
    "art_62": {
        "texte": "Dès l'acceptation par le bénéficiaire, la désignation devient irrévocable. Tout acte de disposition sur la police (rachat, nantissement, avance) nécessite alors l'accord écrit du bénéficiaire acceptant.",
        "portee": "Acceptation bénéficiaire — irrévocabilité et effets"
    },
    "art_63": {
        "texte": "Si le bénéficiaire décède avant l'assuré, sa désignation est caduque et le capital est versé aux héritiers légaux de l'assuré ou au bénéficiaire subsidiaire désigné.",
        "portee": "Décès du bénéficiaire avant l'assuré"
    },
    "art_64": {
        "texte": "Le capital ou la rente garantis au bénéficiaire désigné sont insaisissables par les créanciers du souscripteur. En cas de souscription en vue de frauder les créanciers, le juge peut ordonner la restitution des primes versées.",
        "portee": "Insaisissabilité du capital vie — sauf fraude aux créanciers"
    },
    "art_65": {
        "texte": "L'assurance sur la vie d'un tiers ne peut être souscrite sans le consentement écrit de ce tiers. Si le tiers est mineur ou incapable, l'autorisation du représentant légal est requise en sus.",
        "portee": "Consentement obligatoire de l'assuré tiers"
    },
    "art_66": {
        "texte": "L'assurance de groupe est souscrite par une personne morale (souscripteur) au profit de membres d'une collectivité (adhérents). Les garanties et tarifs sont fixés dans la convention de groupe. Chaque adhérent reçoit une notice d'information.",
        "portee": "Assurance de groupe — définition et notice"
    },
    "art_67": {
        "texte": "L'adhésion à un contrat de groupe résulte d'un bulletin d'adhésion signé par l'adhérent. La compagnie délivre un certificat d'adhésion à chaque membre. Les garanties prennent effet à la date fixée dans le bulletin.",
        "portee": "Bulletin d'adhésion — assurance groupe"
    },
    "art_68": {
        "texte": "En cas de cessation du contrat de groupe, les adhérents bénéficient d'un droit individuel à la portabilité de leurs garanties décès-invalidité pendant 12 mois sans nouvelle formalité médicale.",
        "duree_portabilite_mois": 12,
        "portee": "Portabilité des garanties groupe — 12 mois"
    },
    "art_69": {
        "texte": "Le souscripteur peut résilier le contrat de groupe avec un préavis de 3 mois. Il doit informer les adhérents dans les 15 jours suivant la décision de résiliation pour leur permettre de rechercher une couverture individuelle.",
        "preavis_resiliation_groupe_mois": 3,
        "delai_information_adherents_jours": 15,
        "portee": "Résiliation contrat groupe — préavis et obligations d'information"
    },
    "art_70": {
        "texte": "L'assurance accidents corporels garantit le décès, l'invalidité permanente (IPP) et l'incapacité temporaire de travail (ITT) résultant d'un événement soudain, imprévu et extérieur à la personne de l'assuré.",
        "portee": "Assurance accidents corporels — définition et garanties"
    },
    "art_71": {
        "texte": "Est considéré comme accident au sens des assurances de personnes : tout événement soudain, involontaire, imprévu et extérieur au corps de l'assuré, entraînant une lésion corporelle objectivement constatée.",
        "portee": "Définition légale de l'accident en assurance de personnes"
    },
    "art_72": {
        "texte": "L'évaluation du taux d'invalidité permanente est effectuée par un médecin expert désigné par l'assureur. L'assuré peut demander une contre-expertise à ses frais, ou une expertise amiable contradictoire.",
        "portee": "Évaluation médicale de l'invalidité — expertise et contre-expertise"
    }
})

# ─── LIVRE I : Art. 74-98 ─────────────────────────────────────────────────────

data['livre_I_contrat_assurance']['chapitre_VII_assurance_vie_accidents'] = {
    "art_74": {
        "texte": "En assurance-vie décès, le suicide de l'assuré n'est garanti qu'après un délai de carence d'un an à compter de la prise d'effet du contrat ou de la remise en vigueur après résiliation pour non-paiement.",
        "delai_carence_suicide_ans": 1,
        "portee": "Suicide — délai de carence 1 an"
    },
    "art_75": {
        "texte": "Le bénéficiaire qui a volontairement donné la mort à l'assuré est déchu de ses droits. Le capital est alors versé aux héritiers légaux ou au bénéficiaire subsidiaire.",
        "portee": "Déchéance du bénéficiaire meurtrier"
    },
    "art_76": {
        "texte": "En assurance-vie, la prescription est de dix ans pour les actions du bénéficiaire contre l'assureur à compter du terme du contrat ou de la date du décès. Pour les capitaux non réclamés, le dépôt à la Caisse des Dépôts intervient après 10 ans d'inaction.",
        "delai_prescription_vie_ans": 10,
        "portee": "Prescription décennale — assurance vie"
    },
    "art_77": {
        "texte": "Les contrats collectifs d'assurance-vie obéissent aux règles des assurances de groupe. Le souscripteur répond de l'exactitude des déclarations faites par les adhérents. En cas de fausse déclaration d'un adhérent, seule sa garantie individuelle est affectée.",
        "portee": "Contrats collectifs vie — responsabilité du souscripteur"
    },
    "art_78": {
        "texte": "La rente viagère est un produit d'assurance par lequel l'assureur s'engage à verser à l'assuré une rente périodique jusqu'à son décès, en échange d'une prime unique ou de primes périodiques.",
        "portee": "Définition de la rente viagère"
    },
    "art_79": {
        "texte": "Les calculs actuariels des provisions mathématiques doivent être effectués à partir des tables de mortalité agréées par la CRCA. L'utilisation de tables d'expérience est soumise à approbation préalable de la CRCA.",
        "portee": "Tables de mortalité réglementaires obligatoires"
    },
    "art_80": {
        "texte": "Les entreprises d'assurance-vie doivent distribuer aux assurés au minimum 85% des produits financiers nets attribuables aux contrats d'assurance-vie, sous forme de participation aux bénéfices.",
        "minimum_participation_benefices": 0.85,
        "portee": "Participation aux bénéfices — minimum 85% des produits financiers"
    },
    "art_81": {
        "texte": "Les contrats d'assurance-retraite bénéficient d'un traitement fiscal préférentiel défini par la législation fiscale de chaque État membre. Les rentes de retraite sont imposables à la source lors de leur versement.",
        "portee": "Assurance-retraite — fiscalité déterminée par chaque État membre"
    },
    "art_82": {
        "texte": "La valeur de la prime viagère est calculée actuariellement sur la base des tables et du taux technique agréés par la CRCA.",
        "portee": "Prime viagère — calcul actuariel"
    },
    "art_83": {
        "texte": "Les documents nécessaires au règlement d'un sinistre vie incluent : acte de décès, certificat médical de cause de décès, attestation du bénéficiaire, justificatif d'identité. L'assureur ne peut exiger que les documents strictement nécessaires.",
        "portee": "Documents requis pour le règlement vie"
    },
    "art_84": {
        "texte": "Si l'âge de l'assuré est inexactement déclaré, les sommes assurées sont réduites en proportion des primes payées par rapport aux primes qui auraient dû être payées si l'âge réel avait été connu.",
        "portee": "Correction pour âge inexact — réduction proportionnelle"
    },
    "art_85": {
        "texte": "L'assurance-emprunteur garantit le remboursement du capital restant dû d'un prêt en cas de décès ou d'invalidité de l'emprunteur. Elle est souvent exigée par l'établissement prêteur comme condition du crédit.",
        "portee": "Assurance emprunteur — crédit vie"
    },
    "art_86": {
        "texte": "La réticence dolosive dans un contrat d'assurance-vie entraîne sa nullité, et l'assureur conserve toutes les primes versées à titre d'indemnité. Les héritiers de l'assuré ne peuvent se prévaloir du contrat.",
        "portee": "Nullité pour réticence dolosive vie — conservation des primes"
    },
    "art_87": {
        "texte": "Est en état d'invalidité permanente totale (IPT) l'assuré dont le taux d'incapacité permanente est égal ou supérieur à 66%. Le capital décès ou le capital invalidité est versé intégralement dans ce cas.",
        "seuil_ipt_pct": 66,
        "portee": "Invalidité Permanente Totale — seuil 66%"
    },
    "art_88": {
        "texte": "L'assurance perte d'emploi garantit le paiement d'un revenu de substitution en cas de licenciement économique involontaire. Elle ne couvre pas la démission, la rupture conventionnelle, ni la retraite anticipée.",
        "portee": "Assurance perte d'emploi — licenciement économique uniquement"
    },
    "art_89": {
        "texte": "Les assurances maladie et frais de soins ont pour objet le remboursement ou l'indemnisation des dépenses de santé de l'assuré. Les remboursements sont plafonnés par les actes médicaux figurant à la nomenclature nationale.",
        "portee": "Assurance maladie — frais de soins"
    },
    "art_90": {
        "texte": "Les remboursements de frais médicaux sont effectués sur présentation de justificatifs originaux. L'assureur ne peut refuser un remboursement sans justification écrite.",
        "portee": "Remboursement frais médicaux — obligation de justification du refus"
    },
    "art_91": {
        "texte": "Les frais d'hospitalisation couverts comprennent les frais de séjour, les honoraires médicaux et chirurgicaux, et les frais pharmaceutiques engagés pendant l'hospitalisation, dans la limite des plafonds contractuels.",
        "portee": "Couverture hospitalisation — frais couverts"
    },
    "art_92": {
        "texte": "Les frais de maternité sont couverts sous réserve d'un délai de carence minimum de 9 mois à compter de la souscription, sauf si la grossesse est antérieure à la souscription.",
        "delai_carence_maternite_mois": 9,
        "portee": "Assurance maternité — délai de carence 9 mois"
    },
    "art_93": {
        "texte": "Les maladies préexistantes à la souscription peuvent être exclues ou couvertes sous réserve d'une majoration de prime. L'assureur doit préciser explicitement toute exclusion pour maladie préexistante aux conditions particulières.",
        "portee": "Maladies préexistantes — exclusion ou surprime obligatoirement déclarée"
    },
    "art_94": {
        "texte": "L'assurance accidents corporels garantit les conséquences d'un événement soudain, imprévu et extérieur au corps de l'assuré : décès accidentel, invalidité permanente partielle ou totale, incapacité temporaire de travail.",
        "portee": "Assurance accidents corporels — définition et garanties essentielles"
    },
    "art_95": {
        "texte": "Le capital décès accidentel est versé si l'assuré décède des suites directes d'un accident dans un délai d'un an suivant cet accident.",
        "delai_lien_causal_deces_accident_an": 1,
        "portee": "Décès accidentel — lien de causalité exigé dans l'année"
    },
    "art_96": {
        "texte": "L'expertise médicale est effectuée par un médecin désigné par l'assureur. L'assuré peut demander une contre-expertise. En cas de désaccord, les parties nomment un troisième expert amiable. Les frais sont à la charge de la partie qui perd.",
        "portee": "Expertise médicale accidents — procédure de contre-expertise"
    },
    "art_97": {
        "texte": "Le barème d'invalidité applicable est celui défini aux conditions générales, ou à défaut, le barème légal en vigueur dans l'État membre. Aucun barème ne peut réduire les droits en deçà du barème CIMA.",
        "portee": "Barème d'invalidité — application du barème CIMA en plancher"
    },
    "art_98": {
        "texte": "Les actions en garantie découlant d'un contrat d'assurance accidents corporels se prescrivent par deux ans à compter de l'accident ou de la connaissance par l'assuré des conséquences de cet accident.",
        "delai_prescription_accidents_ans": 2,
        "portee": "Prescription 2 ans — assurance accidents corporels"
    }
}

# ─── LIVRE II : Articles 203-251 manquants ────────────────────────────────────

data['livre_II_assurances_obligatoires'].update({
    "art_203": {
        "texte": "Sont dispensés de l'obligation d'assurance RC automobile : les véhicules militaires en opération, les véhicules de l'État utilisés exclusivement hors voie publique, et les engins de travaux publics utilisés sur chantier fermé.",
        "portee": "Véhicules dispensés d'assurance RC — cas limitatifs"
    },
    "art_204": {
        "texte": "Tout véhicule agricole ou forestier circulant sur voie publique est soumis à l'obligation d'assurance RC automobile. Les tracteurs travaillant exclusivement en champ clos sont dispensés.",
        "portee": "Véhicules agricoles — RC obligatoire sur voie publique"
    },
    "art_206": {
        "texte": "L'assurance temporaire RC automobile peut être souscrite pour une durée de 1 à 30 jours consécutifs. Elle vaut carte rose pour la période couverte. Au-delà de 30 jours, seule une police annuelle est admise.",
        "duree_min_jours": 1,
        "duree_max_jours": 30,
        "portee": "Assurance temporaire RC auto — 1 à 30 jours"
    },
    "art_208": {
        "texte": "La victime ou ses ayants droit doivent déclarer le sinistre au Fonds de Garantie Automobile (FGA) dans un délai d'un an à compter de l'accident si le véhicule responsable n'est pas identifié ou n'est pas assuré.",
        "delai_declaration_fga_ans": 1,
        "portee": "Déclaration sinistre au FGA — délai d'un an"
    },
    "art_209": {
        "texte": "Le FGA peut mandater un expert médical pour l'évaluation des préjudices corporels des victimes. La victime peut demander une contre-expertise médicale. Les frais d'expertise sont à la charge du FGA.",
        "portee": "Expertise médicale FGA — contre-expertise de la victime"
    },
    "art_211": {
        "texte": "Après indemnisation, le FGA est subrogé dans les droits de la victime contre tout responsable du dommage : conducteur non assuré, propriétaire du véhicule non assuré, ou voleur du véhicule.",
        "portee": "Subrogation du FGA — recours contre l'auteur non assuré"
    },
    "art_212": {
        "texte": "Le Fonds de Garantie Automobile est alimenté par une cotisation obligatoire de 2% des primes RC automobile encaissées par chaque compagnie d'assurance membre. La CRCA fixe le taux par arrêté.",
        "taux_cotisation_fga": 0.02,
        "portee": "Financement du FGA — 2% des primes RC auto"
    },
    "art_213": {
        "texte": "En cas d'accident corporel, l'assureur désigne un expert médical dans les 15 jours suivant la demande de la victime. Si l'état de la victime est consolidé, l'expert établit son rapport final dans les 30 jours suivant la consolidation.",
        "delai_designation_expert_jours": 15,
        "delai_rapport_final_jours": 30,
        "portee": "Expertise médicale RC auto — délais réglementaires"
    },
    "art_214": {
        "texte": "Le défaut d'assurance RC automobile est sanctionné par : une amende de 50 000 à 300 000 FCFA, l'immobilisation du véhicule, et le retrait du certificat d'immatriculation jusqu'à régularisation.",
        "amende_min_fcfa": 50000,
        "amende_max_fcfa": 300000,
        "portee": "Sanctions défaut RC auto"
    },
    "art_215": {
        "texte": "Les forces de l'ordre peuvent exiger la présentation de la carte rose lors de tout contrôle routier. Un conducteur sans carte rose valide est passible des sanctions prévues à l'article 214.",
        "portee": "Contrôle de l'assurance RC auto par les forces de l'ordre"
    },
    "art_216": {
        "texte": "La carte verte est l'extension internationale de l'assurance RC automobile aux pays membres du Bureau International de la Carte Verte. Elle est obligatoire pour tout voyage hors des pays CIMA.",
        "portee": "Carte verte — assurance RC internationale"
    },
    "art_217": {
        "texte": "Le coefficient de réduction-majoration (CRM ou bonus-malus) s'applique à la prime RC automobile. La valeur initiale est de 1.00. Elle est réduite de 5% par année sans sinistre responsable (minimum 0.50) et majorée de 25% par sinistre responsable (maximum 3.50).",
        "crm_initial": 1.00,
        "reduction_annuelle_pct": 5,
        "majoration_sinistre_pct": 25,
        "crm_minimum": 0.50,
        "crm_maximum": 3.50,
        "portee": "Bonus-malus CRM — coefficient 0.50 à 3.50"
    },
    "art_218": {
        "texte": "Le CRM est porté à 3.50 en cas de sinistre causé sous l'emprise de l'alcool ou de stupéfiants. Cette majoration est maintenue pendant 3 exercices consécutifs.",
        "crm_alcool": 3.50,
        "duree_majoration_alcool_ans": 3,
        "portee": "Majoration CRM pour alcool — 3.50 pendant 3 ans"
    },
    "art_219": {
        "texte": "L'assureur RC automobile ne peut suspendre ou résilier la garantie au détriment d'une victime déjà identifiée dont le sinistre est en cours d'instruction. La garantie se maintient jusqu'au règlement définitif.",
        "portee": "Maintien de la garantie RC auto pour sinistres en cours"
    },
    "art_221": {
        "texte": "L'assistance en cas de panne ou d'accident (véhicule de remplacement, remorquage, hébergement d'urgence) est une garantie optionnelle de l'assurance automobile.",
        "portee": "Assurance assistance automobile — garantie optionnelle"
    },
    "art_222": {
        "texte": "La garantie dommages tous accidents (DTA) couvre les dommages subis par le véhicule de l'assuré quelle que soit la responsabilité, sous déduction de la franchise contractuelle.",
        "portee": "Garantie DTA — dommages au véhicule assuré"
    },
    "art_223": {
        "texte": "La garantie protection du conducteur couvre les dommages corporels subis par le conducteur responsable de l'accident, exclu de la RC. Elle est fortement recommandée car le conducteur n'est pas tiers vis-à-vis de sa propre police RC.",
        "portee": "Protection du conducteur — garantie corporelle du conducteur responsable"
    },
    "art_224": {
        "texte": "La garantie vol de véhicule est soumise à une déclaration au commissariat de police dans les 24 heures suivant la constatation du vol. La restitution du véhicule retrouvé dans les 30 jours annule l'indemnisation.",
        "delai_declaration_vol_heures": 24,
        "delai_restitution_jours": 30,
        "portee": "Vol de véhicule — déclaration police 24h"
    },
    "art_226": {
        "texte": "Le maître d'ouvrage doit souscrire une assurance RC décennale avant l'ouverture de tout chantier de construction. Cette assurance couvre les dommages compromettant la solidité de l'ouvrage pendant 10 ans à compter de la réception.",
        "duree_garantie_ans": 10,
        "portee": "RC décennale maître d'ouvrage — 10 ans"
    },
    "art_227": {
        "texte": "Tout entrepreneur ou artisan du bâtiment doit souscrire une RC professionnelle couvrant les dommages causés pendant l'exécution des travaux (RC chantier), incluant les dommages aux tiers et à l'ouvrage.",
        "portee": "RC chantier — entrepreneurs du bâtiment"
    },
    "art_228": {
        "texte": "Le syndicat de copropriété doit souscrire une assurance multirisque immeuble couvrant a minima les risques d'incendie, les dégâts des eaux et la RC vis-à-vis des tiers et des copropriétaires.",
        "garanties_minimum": ["Incendie", "Dégâts des eaux", "RC immeuble"],
        "portee": "Assurance copropriété — garanties minimales obligatoires"
    },
    "art_229": {
        "texte": "Le propriétaire bailleur est responsable des dommages causés à ses locataires ou à des tiers résultant d'un défaut d'entretien ou de vices de construction de son immeuble.",
        "portee": "RC propriétaire d'immeuble — responsabilité locataire et tiers"
    },
    "art_230": {
        "texte": "Le locataire est responsable des dommages causés à l'immeuble loué du fait d'incendie ou de dégâts des eaux. La souscription d'une assurance RC locataire est recommandée et peut être imposée par le bail.",
        "portee": "RC locataire — responsabilité incendie et dégâts des eaux"
    },
    "art_233": {
        "texte": "Le transporteur public de voyageurs doit obligatoirement souscrire une assurance RC couvrant les dommages corporels et matériels causés aux passagers, bagages compris.",
        "portee": "RC transport public de voyageurs — obligatoire"
    },
    "art_234": {
        "texte": "Le transporteur de marchandises dangereuses (hydrocarbures, matières radioactives, produits chimiques) doit souscrire une RC renforcée avec des plafonds majorés définis par arrêté spécial.",
        "portee": "RC transport matières dangereuses — plafonds renforcés"
    },
    "art_235": {
        "texte": "Tout professionnel de la chasse doit souscrire une assurance RC couvrant les dommages causés à des tiers lors de l'exercice de la chasse. La carte de chasse ne peut être délivrée sans attestation d'assurance.",
        "portee": "RC chasse obligatoire"
    },
    "art_236": {
        "texte": "Les professions réglementées (médecins, avocats, experts comptables, architectes, notaires) doivent obligatoirement souscrire une assurance RC professionnelle auprès d'une compagnie agréée CRCA.",
        "portee": "RC professionnelle obligatoire — professions réglementées"
    },
    "art_237": {
        "texte": "Les employeurs sont tenus de souscrire une assurance AT/MP (accidents du travail et maladies professionnelles) pour leurs salariés, conformément aux législations nationales de chaque État membre.",
        "portee": "Assurance accidents du travail — obligation employeur"
    },
    "art_238": {
        "texte": "Les entreprises exploitant des installations industrielles présentant des risques pour l'environnement ou le voisinage doivent souscrire une RC exploitation incluant les dommages environnementaux.",
        "portee": "RC exploitation industrielle et environnementale"
    },
    "art_239": {
        "texte": "Les exploitants d'aéronefs civils immatriculés dans un État membre CIMA doivent souscrire une RC aviation couvrant les passagers, les tiers au sol et les dommages aux tiers en survol.",
        "portee": "RC aviation civile — passagers et tiers au sol"
    },
    "art_240": {
        "texte": "Les établissements scolaires et de formation doivent souscrire une RC civile couvrant les dommages causés aux élèves, aux enseignants et aux tiers lors des activités pédagogiques.",
        "portee": "RC établissements scolaires"
    },
    "art_241": {
        "texte": "Les organisateurs de manifestations sportives ou culturelles doivent souscrire une RC organisateur couvrant les dommages causés aux participants et aux spectateurs.",
        "portee": "RC organisateur manifestations"
    },
    "art_242": {
        "texte": "Les établissements accueillant du public (hôtels, restaurants, stades, centres commerciaux) doivent souscrire une RC exploitation couvrant les dommages causés aux clients et visiteurs.",
        "portee": "RC établissements recevant du public (ERP)"
    },
    "art_243": {
        "texte": "Les agents immobiliers, promoteurs et administrateurs de biens doivent souscrire une assurance RC professionnelle et une garantie financière couvrant les fonds de leurs clients.",
        "portee": "RC professionnelle et garantie financière — agents immobiliers"
    },
    "art_244": {
        "texte": "Les pharmaciens doivent souscrire une RC professionnelle couvrant les erreurs de délivrance et les conseils inadaptés causant un préjudice au patient.",
        "portee": "RC pharmaciens — erreurs de délivrance"
    },
    "art_245": {
        "texte": "Les médecins et professionnels de santé exerçant à titre libéral doivent souscrire une RC médicale couvrant les actes fautifs, les erreurs de diagnostic et les complications.",
        "portee": "RC médicale — praticiens de santé libéraux"
    },
    "art_246": {
        "texte": "Les avocats doivent souscrire une RC professionnelle couvrant les erreurs, omissions et négligences dans leur activité de conseil et de représentation en justice.",
        "portee": "RC professionnelle avocats"
    },
    "art_247": {
        "texte": "Les experts comptables et commissaires aux comptes doivent souscrire une RC professionnelle couvrant les erreurs comptables et d'audit ayant causé un préjudice financier.",
        "portee": "RC professionnelle experts comptables et CAC"
    },
    "art_248": {
        "texte": "Les entrepreneurs de transport fluvial circulant sur les voies d'eau des États membres CIMA doivent souscrire une RC navigation intérieure couvrant les dommages aux tiers et à l'environnement aquatique.",
        "portee": "RC navigation intérieure"
    },
    "art_249": {
        "texte": "Les propriétaires d'embarcations de plaisance motorisées doivent souscrire une RC nautique couvrant les dommages causés aux tiers et aux autres embarcations.",
        "portee": "RC nautique embarcations de plaisance"
    },
    "art_250": {
        "texte": "Les établissements bancaires et financiers doivent souscrire une assurance couvrant les risques d'infidélité des préposés, les risques informatiques, et la RC exploitation vis-à-vis de leurs clients.",
        "portee": "Assurances obligatoires établissements bancaires"
    },
    "art_251": {
        "texte": "Tout État membre peut, par arrêté, étendre la liste des assurances obligatoires à d'autres activités professionnelles présentant des risques pour les tiers, dans le respect des dispositions harmonisées du Code CIMA.",
        "portee": "Extension possible des assurances obligatoires par arrêté national"
    }
})

# ─── LIVRE III : Articles manquants ──────────────────────────────────────────

data['livre_III_entreprises_assurance']['agrement'].update({
    "art_304": {
        "texte": "Le dossier d'agrément comprend : les statuts, la liste des actionnaires et dirigeants, le programme d'activité sur 3 ans, la justification du capital libéré, et tout document exigé par la CRCA. L'instruction dure au maximum 6 mois.",
        "delai_instruction_mois": 6,
        "portee": "Dossier d'agrément — contenu et délai 6 mois"
    },
    "art_305": {
        "texte": "Les dirigeants d'une entreprise d'assurance doivent justifier d'une honorabilité irréprochable et d'une expérience professionnelle dans les domaines assurantiels, financiers ou juridiques d'au moins 5 ans.",
        "experience_minimum_ans": 5,
        "portee": "Conditions dirigeants — honorabilité et expérience 5 ans"
    },
    "art_306": {
        "texte": "Le programme d'activité soumis à la CRCA détaille : les branches envisagées, les moyens humains et techniques, les prévisions financières sur 3 ans, et le plan de réassurance prévisionnel.",
        "duree_previsions_ans": 3,
        "portee": "Programme d'activité — contenu minimum"
    },
    "art_307": {
        "texte": "La décision d'agrément est publiée au Journal Officiel de l'État membre concerné. L'exercice de branches non agréées est une infraction grave sanctionnée par retrait d'agrément.",
        "portee": "Publication de l'agrément — Journal Officiel"
    },
    "art_311": {
        "texte": "Les entreprises d'assurance doivent tenir leur comptabilité selon le Plan Comptable Sectoriel des Assurances (PCSA) zone CIMA, qui est obligatoire pour toutes les compagnies agréées.",
        "portee": "Obligation du Plan Comptable Sectoriel Assurances (PCSA)"
    },
    "art_313": {
        "texte": "Les entreprises pratiquant à la fois des opérations vie et non-vie doivent tenir des comptabilités strictement séparées. Les résultats ne peuvent être compensés entre branches.",
        "portee": "Séparation comptable obligatoire vie / non-vie"
    },
    "art_314": {
        "texte": "Le résultat technique de chaque branche est calculé par différence entre les produits techniques (primes acquises, produits financiers techniques) et les charges techniques (sinistres, provisions, commissions, frais).",
        "portee": "Calcul du résultat technique par branche"
    },
    "art_315": {
        "texte": "Le rapport annuel de gestion décrit l'activité de l'exercice, les faits marquants, les résultats techniques et financiers, et les perspectives pour l'exercice suivant.",
        "portee": "Rapport annuel de gestion — contenu obligatoire"
    },
    "art_316": {
        "texte": "Toute entreprise d'assurance doit désigner au moins un commissaire aux comptes agréé par la CRCA. Il certifie les comptes annuels et son rapport est joint aux états déposés à la CRCA.",
        "portee": "Commissaire aux comptes agréé CRCA — obligatoire"
    },
    "art_317": {
        "texte": "Les entreprises d'assurance transmettent à la CRCA tous les états comptables (C1-C20), les rapports des CAC, et toute information sur des faits susceptibles de compromettre leur situation financière.",
        "portee": "Obligation de communication à la CRCA"
    },
    "art_318": {
        "texte": "Les actifs représentatifs des engagements doivent être localisés dans l'État membre où sont souscrits les contrats. Les actifs hors zone CIMA sont limités à 20% des provisions techniques.",
        "limite_actifs_hors_cima_pct": 20,
        "portee": "Localisation des actifs représentatifs"
    },
    "art_319": {
        "texte": "La liste limitative des actifs admis en représentation des provisions techniques est arrêtée par la CRCA. Tout actif ne figurant pas sur cette liste ne peut être comptabilisé en représentation.",
        "portee": "Actifs admis — liste limitative CRCA"
    },
    "art_322": {
        "texte": "Les fonds propres réglementaires comprennent : le capital social libéré, les réserves légales et statutaires, le report à nouveau positif, et les plus-values latentes nettes d'impôt.",
        "portee": "Composition des fonds propres réglementaires"
    },
    "art_323": {
        "texte": "Toute augmentation de capital doit être notifiée à la CRCA préalablement. La CRCA dispose de 30 jours pour s'y opposer si la provenance des fonds compromet l'honorabilité.",
        "delai_opposition_crca_jours": 30,
        "portee": "Augmentation de capital — notification préalable CRCA"
    },
    "art_324": {
        "texte": "Une réduction de capital ne peut être effectuée si elle porte les fonds propres en dessous de la marge de solvabilité réglementaire.",
        "portee": "Réduction de capital — maintien de la marge de solvabilité"
    },
    "art_325": {
        "texte": "La distribution de dividendes est interdite si les provisions techniques ne sont pas intégralement couvertes par des actifs admis ou si les fonds propres sont inférieurs à la marge de solvabilité requise.",
        "portee": "Interdiction de dividendes si solvabilité insuffisante"
    },
    "art_326": {
        "texte": "Toute entreprise dont la marge de solvabilité est inférieure au seuil requis doit transmettre à la CRCA un plan de redressement dans les 90 jours.",
        "delai_plan_redressement_jours": 90,
        "portee": "Plan de redressement obligatoire — délai 90 jours"
    },
    "art_327": {
        "texte": "En cas de risque imminent pour les assurés, la CRCA peut ordonner le gel ou la limitation des transferts d'actifs et des rachats, à titre de mesure conservatoire.",
        "portee": "Mesures conservatoires CRCA — gel des actifs"
    },
    "art_328": {
        "texte": "Lorsque la gestion d'une entreprise présente des irrégularités graves, la CRCA peut désigner un administrateur provisoire qui se substitue aux organes dirigeants avec tous leurs pouvoirs.",
        "portee": "Administrateur provisoire — pouvoirs étendus"
    },
    "art_329": {
        "texte": "Le capital social minimum des entreprises d'assurance est fixé à 3 milliards FCFA pour les sociétés non-vie et 3 milliards FCFA pour les sociétés vie. Ce capital doit être intégralement libéré lors de la constitution.",
        "capital_minimum_non_vie_fcfa": 3000000000,
        "capital_minimum_vie_fcfa": 3000000000,
        "portee": "Capital minimum 3 milliards FCFA (Circulaire 2016-001)"
    },
    "art_329_1": {
        "texte": "Par dérogation à l'article 329, le capital minimum des sociétés de microassurance agréées est fixé à 500 millions FCFA. Elles sont limitées à des produits dont la prime mensuelle ne dépasse pas 5 000 FCFA.",
        "capital_minimum_microassurance_fcfa": 500000000,
        "prime_max_mensuelle_fcfa": 5000,
        "portee": "Microassurance — capital 500M FCFA (Circulaire 2024)"
    },
    "art_330": {
        "texte": "Les entreprises d'assurance nouvellement agréées doivent constituer un fonds de garantie initial égal au tiers de la marge de solvabilité requise avant tout début d'activité.",
        "portee": "Fonds de garantie initial — tiers de la marge de solvabilité"
    },
    "art_331": {
        "texte": "L'agrément est accordé par branche principale. Une entreprise ne peut pratiquer des opérations vie et non-vie simultanément que si elle dispose d'agréments distincts et de gestions séparées.",
        "portee": "Agrément par branche — séparation vie / non-vie"
    },
    "art_332": {
        "texte": "Toute opération de fusion, absorption ou scission impliquant une entreprise d'assurance est soumise à l'agrément préalable de la CRCA rendu dans un délai de 3 mois.",
        "delai_decision_mois": 3,
        "portee": "Fusion, absorption, scission — agrément préalable CRCA"
    },
    "art_333": {
        "texte": "Le transfert de portefeuille est soumis à l'agrément de la CRCA. Les assurés cédés ont un droit d'opposition dans un délai de 2 mois suivant la publication du transfert.",
        "delai_opposition_assures_mois": 2,
        "portee": "Transfert de portefeuille — droit d'opposition des assurés"
    },
    "art_336": {
        "texte": "La CRCA peut placer une entreprise sous surveillance renforcée lorsque sa situation financière se dégrade, même si la marge de solvabilité n'est pas encore insuffisante. L'entreprise transmet alors des états trimestriels supplémentaires.",
        "portee": "Surveillance renforcée CRCA — avant atteinte des seuils"
    },
    "art_339": {
        "texte": "La CRCA peut procéder à des inspections sur place de toute entreprise d'assurance agréée. L'entreprise est tenue de mettre à disposition l'ensemble de ses documents comptables, techniques et de gestion.",
        "portee": "Inspections sur place — pouvoirs des inspecteurs CRCA"
    },
    "art_340": {
        "texte": "L'entreprise inspectée dispose de 30 jours pour répondre aux observations du rapport d'inspection. Ses observations sont jointes au rapport final transmis au collège de la CRCA.",
        "delai_reponse_inspection_jours": 30,
        "portee": "Droit de réponse à l'inspection — 30 jours"
    }
})

data['livre_III_entreprises_assurance']['controle_crca'].update({
    "art_402": {
        "texte": "Les états réglementaires (C1-C20) sont transmis à la CRCA sous format standardisé. Le format électronique est accepté conformément à la circulaire 2020-001.",
        "portee": "Format électronique admis pour les états CRCA"
    },
    "art_403": {
        "texte": "La CRCA peut demander des états spéciaux non prévus au format C1-C20 en cas d'investigation. L'entreprise dispose de 30 jours pour les transmettre.",
        "delai_etats_speciaux_jours": 30,
        "portee": "États spéciaux CRCA — délai 30 jours"
    },
    "art_404": {
        "texte": "La CRCA contrôle la cohérence des états déposés avec les comptes certifiés par le CAC. Tout écart significatif fait l'objet d'une demande d'explication dans les 15 jours.",
        "delai_explication_ecart_jours": 15,
        "portee": "Contrôle de cohérence des états par la CRCA"
    },
    "art_405": {
        "texte": "En cas d'erreur dans les états déposés, l'entreprise peut transmettre des états rectificatifs dans les 30 jours suivant la découverte de l'erreur, sans pénalité si la correction est spontanée.",
        "delai_rectification_jours": 30,
        "portee": "États rectificatifs — correction spontanée sans pénalité"
    },
    "art_406": {
        "texte": "Le retard dans le dépôt des états réglementaires à la CRCA est sanctionné par une amende de 50 000 FCFA par jour de retard, dans la limite de 5 millions FCFA. Au-delà de 90 jours de retard, l'avertissement officiel est prononcé.",
        "amende_par_jour_fcfa": 50000,
        "amende_maximum_fcfa": 5000000,
        "delai_avertissement_jours": 90,
        "portee": "Amende pour retard dépôt états — 50 000 FCFA/jour"
    },
    "art_410": {
        "texte": "L'inspection sur place est déclenchée par décision du collège de la CRCA. Les inspecteurs disposent d'un accès sans restriction à tous les locaux, systèmes informatiques et archives.",
        "portee": "Déclenchement et pouvoirs d'inspection CRCA"
    },
    "art_411": {
        "texte": "L'inspection donne lieu à un procès-verbal signé par les inspecteurs. L'entreprise dispose de 30 jours pour présenter ses observations écrites.",
        "delai_observations_jours": 30,
        "portee": "Procès-verbal d'inspection — droit de réponse 30 jours"
    },
    "art_412": {
        "texte": "La CRCA peut adresser des injonctions à toute entreprise d'assurance lui imposant des mesures correctives dans un délai déterminé. L'injonction est notifiée par lettre recommandée avec accusé de réception.",
        "portee": "Injonctions CRCA — mesures correctives"
    },
    "art_413": {
        "texte": "Avant toute sanction autre que l'avertissement, la CRCA adresse une mise en demeure accordant un délai de 30 jours pour se mettre en conformité.",
        "delai_mise_en_demeure_jours": 30,
        "portee": "Mise en demeure préalable aux sanctions — 30 jours"
    },
    "art_414": {
        "texte": "L'entreprise mise en demeure doit adresser sa réponse par lettre recommandée dans le délai imparti. Le silence vaut acceptation de la mise en demeure.",
        "portee": "Réponse à la mise en demeure — silence vaut acceptation"
    },
    "art_415": {
        "texte": "L'administrateur provisoire est désigné par décision du collège de la CRCA pour une durée maximale de 12 mois renouvelable une fois. Sa mission est de redresser la situation ou d'organiser le transfert de portefeuille.",
        "duree_max_mois": 12,
        "portee": "Administrateur provisoire — durée 12 mois renouvelable"
    },
    "art_416": {
        "texte": "L'administrateur provisoire remet un rapport mensuel au collège de la CRCA. En fin de mission, il présente un rapport final et des recommandations.",
        "periodicite_rapport": "Mensuelle",
        "portee": "Rapport mensuel de l'administrateur provisoire"
    },
    "art_420": {
        "texte": "Le retrait d'agrément est prononcé par le collège de la CRCA après mise en demeure infructueuse. Il entraîne l'arrêt immédiat de toute souscription nouvelle.",
        "portee": "Retrait d'agrément — effet immédiat sur les nouvelles souscriptions"
    },
    "art_421": {
        "texte": "La liquidation judiciaire d'une entreprise d'assurance ne peut être prononcée qu'après retrait d'agrément par la CRCA.",
        "portee": "Liquidation judiciaire — postérieure au retrait d'agrément"
    },
    "art_422": {
        "texte": "Le liquidateur judiciaire dispose des mêmes pouvoirs que l'administrateur provisoire. Les assurés sont créanciers privilégiés de premier rang.",
        "portee": "Liquidateur — assurés créanciers privilégiés de 1er rang"
    },
    "art_423": {
        "texte": "En cas d'insuffisance d'actifs, l'ordre de préférence est : (1) créances des assurés et bénéficiaires, (2) salaires des employés, (3) dettes fiscales et sociales, (4) autres créanciers.",
        "rang_creanciers": ["Assurés et bénéficiaires", "Salariés", "État et CNSS", "Autres créanciers"],
        "portee": "Rang des créanciers en liquidation — assurés en 1er"
    },
    "art_424": {
        "texte": "La liquidation d'une entreprise d'assurance doit être menée à terme dans un délai maximum de 3 ans. La CRCA peut proroger ce délai d'un an en cas de contentieux complexe.",
        "duree_max_liquidation_ans": 3,
        "portee": "Durée maximale de liquidation — 3 ans"
    },
    "art_425": {
        "texte": "Si les actifs sont insuffisants pour désintéresser les assurés, la CRCA peut faire appel au Fonds de Garantie des Assurés pour combler le déficit.",
        "portee": "Fonds de Garantie des Assurés — intervention si insolvabilité"
    },
    "art_426": {
        "texte": "Si un repreneur agréé se manifeste avant liquidation, la CRCA favorise le transfert forcé du portefeuille. Les assurés sont informés par courrier recommandé au moins 2 mois avant le transfert.",
        "delai_information_assures_mois": 2,
        "portee": "Transfert forcé de portefeuille — alternative à la liquidation"
    },
    "art_427": {
        "texte": "Toute décision de retrait d'agrément, liquidation ou transfert forcé est publiée dans les journaux nationaux et dans le bulletin officiel de la CRCA. Les assurés ont 30 jours pour déclarer leurs créances.",
        "delai_declaration_creances_jours": 30,
        "portee": "Publication officielle — 30 jours pour déclarer les créances"
    },
    "art_428": {
        "texte": "Pendant la procédure de transfert ou de liquidation, les sinistres survenus avant la décision de retrait restent garantis.",
        "portee": "Maintien des garanties pour sinistres survenus avant le retrait"
    },
    "art_429": {
        "texte": "Les litiges entre une entreprise d'assurance et un assuré peuvent être soumis à la procédure d'arbitrage de la CRCA. L'arbitrage CRCA est obligatoire avant toute action judiciaire transfrontalière.",
        "portee": "Arbitrage CRCA — obligatoire avant action transfrontalière"
    },
    "art_430": {
        "texte": "Les décisions du collège de la CRCA peuvent faire l'objet d'un recours devant le tribunal administratif de l'État membre du siège social dans un délai de 60 jours suivant leur notification.",
        "delai_recours_jours": 60,
        "portee": "Recours contre les décisions CRCA — délai 60 jours"
    }
})

# ─── LIVRE IV : Articles manquants ───────────────────────────────────────────

data['livre_IV_intermediaires'].update({
    "art_504": {
        "texte": "Pour exercer comme courtier d'assurance : (1) être une personne physique ou morale, (2) justifier d'un capital minimum ou d'une caution bancaire, (3) détenir une assurance RC professionnelle, (4) obtenir la carte professionnelle.",
        "portee": "Conditions d'exercice du courtage — quatre conditions cumulatives"
    },
    "art_505": {
        "texte": "L'autorité nationale de contrôle des assurances tient un registre public des courtiers agréés mentionnant la dénomination, l'adresse, le numéro d'agrément et les branches autorisées.",
        "portee": "Registre public des courtiers"
    },
    "art_506": {
        "texte": "La RC professionnelle du courtier doit avoir un plafond minimum de 30 millions FCFA par sinistre et 60 millions FCFA par an, souscrite auprès d'une compagnie agréée différente du courtier.",
        "plafond_par_sinistre_fcfa": 30000000,
        "plafond_annuel_fcfa": 60000000,
        "portee": "RC professionnelle courtier — plafond 30M/60M FCFA"
    },
    "art_507": {
        "texte": "Le courtier doit disposer d'une garantie financière distincte de son patrimoine propre d'un minimum de 10 millions FCFA pour couvrir les fonds des clients.",
        "garantie_financiere_minimum_fcfa": 10000000,
        "portee": "Garantie financière courtier — 10M FCFA minimum"
    },
    "art_508": {
        "texte": "Le courtier est tenu à un devoir de conseil : il analyse les besoins du client, présente des options adaptées documentées, et conseille le produit le plus adéquat quel que soit son intérêt commercial propre.",
        "portee": "Devoir de conseil du courtier — intérêt du client primordial"
    },
    "art_509": {
        "texte": "Le courtier doit déclarer par écrit à son client tout conflit d'intérêt potentiel, notamment lorsqu'il perçoit des rémunérations au-delà des commissions standard de la compagnie recommandée.",
        "portee": "Déclaration obligatoire des conflits d'intérêt — forme écrite"
    },
    "art_511": {
        "texte": "Le démarchage à domicile ou par voie électronique pour faire souscrire une assurance est réglementé. L'agent ou le courtier doit s'identifier, présenter sa carte professionnelle et remettre une documentation préalable.",
        "portee": "Règles de démarchage — identification obligatoire"
    },
    "art_512": {
        "texte": "Tout contrat souscrit à la suite d'un démarchage à domicile bénéficie d'un droit de rétractation de 14 jours calendaires. L'assureur doit rembourser toute prime perçue pendant ce délai si la rétractation est exercée.",
        "delai_retractation_jours": 14,
        "portee": "Droit de rétractation — 14 jours pour les contrats démarchés"
    },
    "art_513": {
        "texte": "La convention de présentation entre un agent général et sa compagnie mandante doit être conclue par écrit, précisant les branches déléguées, les limites de souscription et les conditions de résiliation.",
        "portee": "Convention de présentation agent — forme écrite obligatoire"
    },
    "art_514": {
        "texte": "La résiliation de la convention de présentation par la compagnie mandante doit être notifiée avec un préavis minimum de 3 mois. En cas de faute grave de l'agent, le préavis n'est pas requis.",
        "preavis_minimum_mois": 3,
        "portee": "Résiliation convention agent — préavis 3 mois"
    },
    "art_515": {
        "texte": "L'agent général a droit à une indemnité de résiliation équivalente à 2 ans de commissions brutes en cas de résiliation sans faute par la compagnie.",
        "indemnite_resiliation_annees_commissions": 2,
        "portee": "Indemnité de résiliation agent — 2 ans de commissions"
    },
    "art_516": {
        "texte": "La clause de non-concurrence imposée à l'agent général est valable si elle est limitée à 2 ans, à une zone géographique précise, et compensée par une indemnité.",
        "duree_max_non_concurrence_ans": 2,
        "portee": "Clause de non-concurrence — 2 ans maximum avec indemnité"
    },
    "art_517": {
        "texte": "Le portefeuille de l'agent général appartient à la compagnie mandante. À la cessation de la convention, l'agent ne peut contacter les assurés pour les déplacer vers un concurrent pendant la période de non-concurrence.",
        "portee": "Propriété du portefeuille — appartient à la compagnie mandante"
    },
    "art_518": {
        "texte": "La cession du portefeuille de courtage requiert l'accord de la CRCA si le portefeuille dépasse 500 millions FCFA de primes annuelles gérées.",
        "seuil_accord_crca_fcfa": 500000000,
        "portee": "Cession portefeuille courtage — accord CRCA si > 500M FCFA"
    },
    "art_519": {
        "texte": "La compagnie mandante est solidairement responsable des actes professionnels de ses agents généraux dans l'exercice de leur mandat. Elle ne peut s'exonérer vis-à-vis des tiers lésés.",
        "portee": "Responsabilité solidaire compagnie-agent vis-à-vis des tiers"
    },
    "art_522": {
        "texte": "La commission disciplinaire nationale peut prononcer : avertissement, blâme, suspension temporaire (1 à 24 mois), retrait définitif de la carte professionnelle.",
        "sanctions": ["Avertissement", "Blâme", "Suspension 1-24 mois", "Retrait définitif"],
        "portee": "Sanctions professionnelles des intermédiaires"
    },
    "art_523": {
        "texte": "Le retrait de la carte professionnelle est inscrit au registre national des intermédiaires. La personne ne peut exercer aucune fonction d'intermédiaire pendant la durée du retrait.",
        "portee": "Retrait de carte — inscription au registre national"
    },
    "art_524": {
        "texte": "Après un retrait de carte pour motif disciplinaire, la réhabilitation peut être demandée après 3 ans de bonne conduite.",
        "delai_rehabilitation_ans": 3,
        "portee": "Réhabilitation professionnelle — après 3 ans"
    },
    "art_525": {
        "texte": "Les intermédiaires d'assurance sont soumis à une obligation de formation continue de 20 heures par an couvrant les réglementations CIMA, les techniques d'assurance et la déontologie.",
        "heures_formation_annuelles": 20,
        "portee": "Formation continue intermédiaires — 20h/an agréées CRCA"
    },
    "art_530": {
        "texte": "Les associations professionnelles d'agents et de courtiers représentent leurs membres auprès de la CRCA et des autorités nationales, et participent aux consultations réglementaires.",
        "portee": "Associations professionnelles — rôle consultatif auprès de la CRCA"
    },
    "art_535": {
        "texte": "Les associations professionnelles doivent adopter un code de déontologie approuvé par la CRCA fixant les règles de conduite, de loyauté et de confidentialité.",
        "portee": "Code de déontologie — adopté par les associations, approuvé CRCA"
    },
    "art_540": {
        "texte": "Les intermédiaires transmettent à l'autorité nationale des statistiques annuelles de production (primes placées par compagnie et par branche). Ces statistiques alimentent le suivi du marché.",
        "portee": "Reporting statistique annuel des intermédiaires"
    },
    "art_545": {
        "texte": "Les intermédiaires exerçant avant l'entrée en vigueur de la présente réglementation disposent de 18 mois pour se mettre en conformité avec les exigences de capital, de RC professionnelle et de garantie financière.",
        "delai_conformite_mois": 18,
        "portee": "Dispositions transitoires — délai de conformité 18 mois"
    }
})

# ─── LIVRE V : Articles manquants ─────────────────────────────────────────────

data['livre_V_dispositions_diverses'].update({
    "art_602": {
        "texte": "La microassurance est définie comme un mécanisme de protection visant les populations à faibles revenus, avec des primes inférieures à 5 000 FCFA par mois et des garanties simplifiées.",
        "prime_max_mensuelle_fcfa": 5000,
        "portee": "Microassurance — définition et régime allégé"
    },
    "art_603": {
        "texte": "Le paiement des primes d'assurance par monnaie électronique (mobile money, portefeuille numérique) est autorisé dans toute la zone CIMA. L'assureur délivre un accusé de réception électronique valant quittance.",
        "portee": "Mobile money — paiement de primes autorisé"
    },
    "art_604": {
        "texte": "La signature électronique qualifiée d'un contrat d'assurance a la même valeur juridique que la signature manuscrite. Le contrat électronique est opposable.",
        "portee": "Signature électronique — valeur équivalente à la signature manuscrite"
    },
    "art_605": {
        "texte": "Les conditions particulières d'un contrat d'assurance peuvent être transmises en format électronique. L'assureur doit s'assurer que l'assuré a reçu ses conditions dans un délai de 15 jours.",
        "portee": "Contrat numérique — confirmation de réception obligatoire"
    },
    "art_606": {
        "texte": "Les données personnelles des assurés sont protégées conformément aux réglementations nationales. L'assureur ne peut les céder à des tiers sans le consentement écrit de l'assuré, sauf obligation légale.",
        "portee": "Protection des données personnelles des assurés"
    },
    "art_607": {
        "texte": "Chaque État membre met en place un service de médiation de l'assurance, indépendant des compagnies, pour traiter les litiges entre assurés et assureurs. La médiation est gratuite et préalable à toute action judiciaire.",
        "portee": "Médiation de l'assurance — service indépendant gratuit"
    },
    "art_608": {
        "texte": "Les parties à un contrat d'assurance peuvent convenir d'une clause d'arbitrage. L'arbitre est désigné par accord commun ou par le président du tribunal compétent.",
        "portee": "Arbitrage contractuel — validité des clauses compromissoires"
    },
    "art_609": {
        "texte": "Toute publicité pour des produits d'assurance doit être loyale, claire et non trompeuse. Elle doit mentionner le nom de la compagnie agréée, les garanties essentielles et les exclusions principales.",
        "portee": "Publicité assurance — loyauté et interdiction publicité trompeuse"
    },
    "art_611": {
        "texte": "Les entreprises d'assurance sont assujetties aux obligations de lutte contre le blanchiment de capitaux (LBC/FT). Elles déclarent les transactions suspectes à la CENTIF (cellule nationale de renseignement financier).",
        "portee": "LBC/FT — déclaration de soupçon à la CENTIF"
    },
    "art_612": {
        "texte": "L'assureur doit identifier et vérifier l'identité de tout souscripteur avant la prise d'effet du contrat (KYC). Pour les personnes morales, la vérification porte aussi sur le bénéficiaire effectif.",
        "portee": "KYC — identification obligatoire avant souscription"
    },
    "art_613": {
        "texte": "Les Personnes Politiquement Exposées (PPE) font l'objet de diligences renforcées. Leur souscription est soumise à l'approbation de la direction générale de l'assureur.",
        "portee": "Diligences renforcées — PPE et listes de sanctions"
    },
    "art_614": {
        "texte": "En cas d'inscription d'un client sur une liste de gel des avoirs (ONU, FATF), l'assureur gèle immédiatement les sommes dues et notifie la CENTIF.",
        "portee": "Gel des avoirs — gel immédiat sur listes ONU/FATF"
    },
    "art_615": {
        "texte": "Pour toute opération d'assurance-vie supérieure à 5 millions FCFA, l'assureur doit identifier et vérifier le bénéficiaire effectif (UBO). Cette information est conservée 10 ans.",
        "seuil_ubo_fcfa": 5000000,
        "duree_conservation_ans": 10,
        "portee": "Bénéficiaires effectifs (UBO) — identification > 5M FCFA"
    },
    "art_621": {
        "texte": "Les placements en actifs non liquides ne peuvent dépasser 40% des provisions techniques. L'assureur doit disposer en permanence d'actifs liquides suffisants pour ses engagements à court terme.",
        "limite_actifs_non_liquides_pct": 40,
        "portee": "Limite des actifs non liquides — 40% des provisions"
    },
    "art_622": {
        "texte": "Les placements en immeubles sont limités aux immeubles productifs de revenus situés dans les États membres CIMA, dans la limite de 30% des actifs admis. Les immeubles occupés par l'assureur sont limités à 10%.",
        "limite_immobilier_total_pct": 30,
        "limite_immobilier_occupe_pct": 10,
        "portee": "Immobilier admis — 30% dont 10% occupé"
    },
    "art_623": {
        "texte": "Les prêts hypothécaires de premier rang sont admis dans la limite de 20% des actifs admis, à condition d'être garantis à hauteur de 120% de la créance.",
        "limite_prets_hypothecaires_pct": 20,
        "garantie_minimum_pct": 120,
        "portee": "Prêts hypothécaires admis — 20%, garantis à 120%"
    },
    "art_624": {
        "texte": "Les dépôts dans un seul établissement bancaire ne peuvent excéder 10% des actifs admis. La limite globale des dépôts bancaires est de 40%.",
        "limite_par_banque_pct": 10,
        "limite_totale_depots_pct": 40,
        "portee": "Dépôts bancaires — 10% par établissement, 40% au total"
    },
    "art_625": {
        "texte": "L'assureur doit diversifier ses actifs entre au moins 5 catégories d'actifs admis. Aucune catégorie (hors obligations d'État) ne peut représenter plus de 40% des actifs admis.",
        "categories_minimum": 5,
        "portee": "Obligation de diversification des placements"
    },
    "art_626": {
        "texte": "Les placements hors zone CIMA sont admis dans la limite de 20% des actifs représentatifs, uniquement dans des valeurs bénéficiant d'une notation minimum BBB.",
        "limite_hors_zone_cima_pct": 20,
        "notation_minimum": "BBB",
        "portee": "Actifs hors zone CIMA — 20% maximum, notation BBB"
    },
    "art_627": {
        "texte": "L'assureur transmet à la CRCA un état annuel de ses placements (état C4) détaillant chaque actif par catégorie, valeur d'acquisition et valeur de marché. Certifié par le CAC.",
        "portee": "Rapport annuel placements (C4) — certifié par le CAC"
    },
    "art_628": {
        "texte": "Les entreprises d'assurance réalisent annuellement des tests de résistance (stress tests) simulant des scénarios adverses : chute des marchés de 30%, hausse des sinistres de 50%, catastrophe naturelle majeure.",
        "scenarios": ["Chute marchés -30%", "Hausse sinistres +50%", "Catastrophe naturelle majeure"],
        "portee": "Stress tests annuels obligatoires"
    },
    "art_629": {
        "texte": "L'ORSA (Own Risk and Solvency Assessment) est réalisé annuellement. Il identifie les risques principaux, quantifie leur impact et démontre la capacité à maintenir la solvabilité sous stress sur 3 ans.",
        "horizon_ans": 3,
        "portee": "ORSA — évaluation interne des risques annuelle"
    },
    "art_631": {
        "texte": "L'actuaire responsable doit être titulaire d'une qualification actuarielle reconnue par la CRCA (Fellow IAA, ISFA ou équivalent) et avoir au moins 5 ans d'expérience en assurance.",
        "experience_minimum_ans": 5,
        "portee": "Qualifications de l'actuaire responsable"
    },
    "art_632": {
        "texte": "Le rapport actuariel annuel certifie le niveau des provisions techniques, les méthodes de calcul utilisées, et tout risque pouvant affecter la solvabilité.",
        "portee": "Rapport actuariel — certification des provisions et risques"
    },
    "art_633": {
        "texte": "L'actuaire responsable ne peut pas être actionnaire détenant plus de 5% du capital ni avoir de lien familial direct avec la direction générale. Son indépendance est une condition de validité.",
        "portee": "Indépendance de l'actuaire"
    },
    "art_634": {
        "texte": "Les tables de mortalité utilisées pour les calculs actuariels vie sont celles publiées par la CRCA. L'utilisation de tables d'expérience est soumise à validation préalable par la CRCA.",
        "portee": "Tables de mortalité CRCA — validation préalable pour tables d'expérience"
    },
    "art_635": {
        "texte": "Les méthodes actuarielles admises pour le calcul des provisions non-vie (PSAP) sont : dossier par dossier, Chain-Ladder, Bornhuetter-Ferguson. Tout changement de méthode doit être signalé à la CRCA.",
        "methodes_admises": ["Dossier par dossier", "Chain-Ladder", "Bornhuetter-Ferguson"],
        "portee": "Méthodes actuarielles PSAP — liste CRCA"
    },
    "art_636": {
        "texte": "Le rapport ORSA inclut des scénarios adverses avec horizon de projection de 3 ans minimum. L'assureur démontre sa capacité à maintenir un ratio de solvabilité supérieur à 100%.",
        "horizon_projection_ans": 3,
        "portee": "ORSA scénarios adverses — horizon 3 ans"
    },
    "art_637": {
        "texte": "Le comité d'audit est obligatoire pour les entreprises dont les provisions techniques dépassent 10 milliards FCFA. Il comprend au moins 3 membres dont la majorité sont des administrateurs indépendants.",
        "seuil_comite_audit_fcfa": 10000000000,
        "membres_minimum": 3,
        "portee": "Comité d'audit obligatoire — provisions > 10 Mds FCFA"
    },
    "art_638": {
        "texte": "Le système de contrôle interne comprend les procédures de souscription, de gestion des sinistres, de placement et de conformité réglementaire. Un rapport annuel est remis au conseil d'administration.",
        "portee": "Contrôle interne — rapport annuel au conseil"
    },
    "art_639": {
        "texte": "Tout employé ou dirigeant peut signaler anonymement au régulateur des violations de la réglementation CIMA sans risquer de représailles.",
        "portee": "Protection des lanceurs d'alerte — whistleblowing"
    },
    "art_640": {
        "texte": "Les modifications apportées au Code CIMA par le Conseil des Ministres entrent en vigueur à la date fixée par le règlement modificateur ou à la date de publication dans le bulletin officiel de la CIMA.",
        "portee": "Entrée en vigueur des modifications au Code CIMA"
    }
})

# ─── LIVRE VI : Articles manquants ────────────────────────────────────────────

data['livre_VI_reassurance'].update({
    "art_702": {
        "texte": "La réassurance facultative porte sur des risques individuels cédés au cas par cas. La réassurance traité porte sur l'ensemble d'un portefeuille selon des termes convenus d'avance. Les deux formes sont admises.",
        "portee": "Réassurance facultative vs traité — définitions"
    },
    "art_703": {
        "texte": "Le taux de commission versé par le réassureur à la cédante est librement négocié. Il figure dans le traité et ne peut être modifié en cours de traité sans avenant.",
        "portee": "Commission de réassurance — librement négociée"
    },
    "art_704": {
        "texte": "La clause de participation aux bénéfices (profit commission) permet à la cédante de récupérer une partie des bénéfices réalisés sur le traité si la sinistralité est favorable.",
        "portee": "Profit commission — participation aux bénéfices de la cédante"
    },
    "art_705": {
        "texte": "La déclaration des sinistres au réassureur intervient dès que l'estimation dépasse le seuil de pleine rétention. Les sinistres graves (au-delà de 5 fois la rétention) sont notifiés immédiatement.",
        "portee": "Déclaration sinistres au réassureur"
    },
    "art_706": {
        "texte": "Le cash-call est un appel de fonds immédiat auprès du réassureur pour les sinistres graves. Le réassureur doit payer le cash-call dans les 30 jours suivant la demande documentée.",
        "delai_paiement_cash_call_jours": 30,
        "portee": "Cash-call — paiement dans 30 jours"
    },
    "art_707": {
        "texte": "La cédante peut exiger du réassureur un dépôt de réassurance pour garantir le paiement des sinistres futurs.",
        "portee": "Dépôt de réassurance — garantie des engagements"
    },
    "art_708": {
        "texte": "Les traités annuels prennent effet au 1er janvier et se terminent au 31 décembre. Les traités pluriannuels peuvent être souscrits pour 3 ans maximum.",
        "duree_max_pluriannuel_ans": 3,
        "portee": "Durée des traités — annuels ou pluriannuels 3 ans max"
    },
    "art_709": {
        "texte": "La résiliation d'un traité de réassurance requiert un préavis de 3 mois sauf clause résolutoire expressément prévue (manquement grave, insolvabilité).",
        "preavis_resiliation_mois": 3,
        "portee": "Résiliation traité — préavis 3 mois"
    },
    "art_711": {
        "texte": "Les traités de réassurance peuvent contenir une clause compromissoire d'arbitrage. Le siège de l'arbitrage est librement choisi par les parties.",
        "portee": "Arbitrage réassurance — clause compromissoire valide"
    },
    "art_712": {
        "texte": "Le droit applicable aux traités est librement choisi. En l'absence de choix, le droit du pays du siège social de la cédante s'applique.",
        "portee": "Droit applicable — liberté de choix, défaut : droit de la cédante"
    },
    "art_713": {
        "texte": "Un traité peut couvrir des risques localisés dans plusieurs États membres CIMA simultanément (traité régional).",
        "portee": "Traité régional CIMA — couverture multi-États membres"
    },
    "art_714": {
        "texte": "La réassurance vie est soumise à des règles spécifiques. Le réassureur vie doit être agréé pour les opérations vie et disposer d'une notation minimum A-.",
        "notation_minimum_reassureur_vie": "A-",
        "portee": "Réassurance vie — notation A- minimum"
    },
    "art_715": {
        "texte": "La rétrocession est autorisée. Le réassureur qui rétrocède reste responsable envers la cédante de ses engagements initiaux.",
        "portee": "Rétrocession autorisée"
    },
    "art_716": {
        "texte": "Les créances sur réassureurs ne sont admises en représentation que si les réassureurs bénéficient d'une notation BBB ou supérieure (S&P, Moody's, Fitch, AM Best).",
        "notation_minimum": "BBB",
        "portee": "Notation BBB minimum — créances réassurance admises"
    },
    "art_717": {
        "texte": "La CRCA publie chaque année une liste des réassureurs agréés pour la zone CIMA.",
        "portee": "Liste CRCA des réassureurs agréés — publiée annuellement"
    },
    "art_718": {
        "texte": "Les cédantes sont encouragées à céder en priorité aux réassureurs locaux et africains. Africa Re bénéficie d'une préférence de premier cession.",
        "portee": "Priorité aux réassureurs africains"
    },
    "art_719": {
        "texte": "Africa Re (Société Africaine de Réassurance, Lagos) est le réassureur panafricain prioritaire. Chaque cédante doit lui offrir au moins 5% de chaque traité.",
        "quota_africa_re_pct": 5,
        "portee": "Africa Re — droit de préférence de 5% sur chaque traité"
    },
    "art_720": {
        "texte": "CICA-Re (siège à Lomé) est le réassureur institutionnel de la zone CIMA. Les cédantes sont incitées à lui céder en priorité après Africa Re.",
        "siege": "Lomé, Togo",
        "portee": "CICA-Re — réassureur institutionnel zone CIMA"
    },
    "art_721": {
        "texte": "Le plan de réassurance annuel (état C20) comprend la liste de tous les traités, les réassureurs participants, leurs notations, les plafonds et rétentions. Il est soumis à la CRCA avant le 31 janvier.",
        "echeance": "31 janvier",
        "portee": "Plan de réassurance C20 — avant 31 janvier"
    },
    "art_722": {
        "texte": "La CRCA contrôle la conformité du plan de réassurance dans les 60 jours suivant son dépôt. Elle peut exiger des modifications si les rétentions semblent inadaptées.",
        "delai_controle_jours": 60,
        "portee": "Contrôle du plan de réassurance — 60 jours"
    },
    "art_723": {
        "texte": "La CRCA peut refuser un traité non conforme. La cédante dispose de 30 jours pour soumettre un plan alternatif.",
        "delai_plan_alternatif_jours": 30,
        "portee": "Refus CRCA d'un traité non conforme"
    },
    "art_724": {
        "texte": "Les créances sur réassureurs sont admises en représentation à 80% de leur montant nominal pour tenir compte du risque de contrepartie.",
        "limite_admission_pct": 80,
        "portee": "Créances réassurance — admises à 80%"
    },
    "art_725": {
        "texte": "La CRCA peut instaurer un pool obligatoire de réassurance pour certains grands risques ou risques catastrophes si le marché individuel ne peut les absorber.",
        "portee": "Pool obligatoire CRCA — grands risques ou catastrophes"
    },
    "art_726": {
        "texte": "En matière de microassurance, les microassureurs peuvent constituer une réserve d'égalisation interne à la place de traités formels, sous réserve d'approbation CRCA.",
        "portee": "Microassurance — réassurance allégée"
    },
    "art_727": {
        "texte": "Les comptes courants de réassurance font l'objet d'un arrêté semestriel. Les soldes nets sont réglés dans les 90 jours. Les intérêts de retard courent après ce délai.",
        "periodicite_arrete": "Semestrielle",
        "delai_reglement_jours": 90,
        "portee": "Comptes courants réassurance — arrêté semestriel, règlement 90j"
    },
    "art_728": {
        "texte": "Les traités conclus par voie électronique sont valides si les parties ont signé un accord cadre de dématérialisation préalable.",
        "portee": "Traités électroniques — valides avec accord cadre"
    },
    "art_729": {
        "texte": "Les cédantes transmettent à la CRCA des rapports trimestriels sur la sinistralité des traités en cours, joints à l'état C8.",
        "portee": "Reporting trimestriel réassurance"
    },
    "art_730": {
        "texte": "Le non-respect du plan de réassurance approuvé est sanctionné par une amende de 500 000 à 5 millions FCFA et peut entraîner une suspension de nouvelles souscriptions.",
        "amende_min_fcfa": 500000,
        "amende_max_fcfa": 5000000,
        "portee": "Sanctions non-respect plan réassurance — amende 500K-5M FCFA"
    }
})

# ─── Sauvegarder ──────────────────────────────────────────────────────────────

with open(JSON_PATH, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("JSON mis a jour avec succes !")

def compter_articles(obj):
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith('art_'):
                count += 1
            else:
                count += compter_articles(v)
    return count

with open(JSON_PATH, encoding='utf-8') as f:
    data2 = json.load(f)

total = compter_articles(data2)
print(f"Total articles apres mise a jour : {total}")

# Audit par livre
livres_check = {
    'Livre I': data2.get('livre_I_contrat_assurance', {}),
    'Livre II': data2.get('livre_II_assurances_obligatoires', {}),
    'Livre III': data2.get('livre_III_entreprises_assurance', {}),
    'Livre IV': data2.get('livre_IV_intermediaires', {}),
    'Livre V': data2.get('livre_V_dispositions_diverses', {}),
    'Livre VI': data2.get('livre_VI_reassurance', {}),
}
for nom, obj in livres_check.items():
    c = compter_articles(obj)
    print(f"  {nom}: {c} articles")
