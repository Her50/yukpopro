# -*- coding: utf-8 -*-
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
markers = [
    "Caisse du jour", "En attente", "En cours",
    "souhaitez-vous", "Ouvrir le hub", "Créer une infographie",
    "Rédiger un document", "Scanner un document", "Transcrire un audio",
    "Gérer les travaux", "Devis & factures", "Profondeur du document",
    "Type de document attendu", "Formater en", "Document scanné",
    "Notes manuscrites", "Microphone non accessible", "Enregistrement en cours",
    "Contexte pays", "Décrivez librement", "Collez ici",
    "Texte transféré", "Source : ", "Glissez une image", "Numérisation en cours",
    "Numériser", "Effacer", "Crédits ajoutés", "Utilisateur bloqué",
    "Utilisateur débloqué", "utilisateur(s)", "appel(s)",
    "Seuils de consommation", "Crédits consommés", "Nombre d'appels",
    "Période d'analyse", "Rôle ciblé", "IDs utilisateurs",
    "Montant invalide", "Liste IDs invalide", "Au moins un seuil",
    "Erreur distribution", "Distribuer ", "Distribué à",
    "Chargement des revenus", "Impossible de charger",
    "recharge(s)", "client(s)", "Aucune recharge sur la période",
    "Utilisateurs actifs", "Utilisateurs précis", "Selon seuils",
    "valeur par bénéficiaire", "Solde actuel", "crédits Yukpo",
    "Total consommé", "Tarification Yukpo", "Découverte", "Petit usage",
    "Recharges rapides", "Recharge personnalisée", "Appels totaux",
    "Valeur consommée", "Modules utilisés", "Top modules consommateurs",
    "Historique récent", "Aucune consommation", "Recharger ",
    "Initier le paiement", "Paiement initié",
    "d'usage restant", "depuis création", "0,6 FCFA",
    "Aucune recharge effectuée", "Erreur initiation",
    "Erreur confirmation", "Crédits ajoutés", "Montant (FCFA",
    "d'usage", "Paiement initié", "Usage régulier", "Travail intensif",
    "Volume élevé", "Populaire", "Rédaction Yukpo", "Audio Yukpo",
    "Traduction Yukpo", "Infographie", "Mes Documents", "Yukpo Secrétariat",
    "Forfait ", "Multi-page Yukpo", "Impression standard",
    "Événementiel", "Grand format", "Réseaux sociaux", "Officiel /",
    "Format personnalisé", "crédits", "Aperçu infographie",
    "Bonjour {{name}}", "Reste à régler", "Le règlement",
    "WhatsApp non envoyé", "Rédaction document IA",
    "Saisie / Retranscription", "Scan / Numérisation",
    "Transcription audio", "Infographie / Visuel",
    "Création de flyer", "Impression / Repro", "Autre type de travail",
    "Espèces", "Virement", "Chèque", "Préférences",
    "clients enregistrés", "commandes", "Total payé",
    "Dernière visite", "votre document est prêt",
    "Profondeur", "Court", "Dicter", "Importer", "Arrêter",
    "Reformuler", "Convertir", "Améliorer", "Reformulation",
    "Numéro WhatsApp", "Description du travail", "Type de travail",
    "Acompte reçu", "Reste :", "Client notifié", "Terminer le travail",
    "Notifier le client", "Erreur terminaison", "Remplissez tous",
    "bons de travail", "Format international", "Numéro invalide",
    "Confirmer le numéro", "automatiquement", "(laisser vide pour",
    "Cordialement", "à régler", "à jour, merci",
]
for lang in ["en","es","pt","ar","de"]:
    p = os.path.join(HERE, f"{lang}.json")
    s = open(p, encoding="utf-8").read()
    found = []
    for m in markers:
        if m in s:
            found.append(m)
    print(f"{lang}: {len(found)} FR markers remaining")
    if found:
        for m in found[:30]:
            print("   -", m)
