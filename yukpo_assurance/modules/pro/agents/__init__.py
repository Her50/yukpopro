"""
Agents spécialisés par métier pour la plateforme Pro.

Agents disponibles :
  - AgentComptable    : Comptabilité, fiscalité SYSCOHADA, IRPP, TVA, IS
  - AgentDRH          : Ressources humaines, droit social africain, paie CNPS
  - AgentDAF          : Direction financière, ratios, cashflow, investissement
  - AgentJuriste      : Droit OHADA, contrats, contentieux, conformité
  - AgentBanquier     : Crédit, KYC/AML, marchés financiers BRVM, TEG
  - AgentIngenieur    : Gestion de projets CPM, marchés publics ARMP, BTP, normes
  - AgentDAA          : Analyse de données, statistiques, visualisation pandas
  - AgentCommercial   : Commerce, pricing, pipeline, business plan, étude de marché
  - AgentONG          : ONG/Développement — logframes, budgets bailleurs (DFID/AFD/BM/UE), M&E
  - AgentMicrofinance : SFD/IMF — scoring crédit, PAR, ratios prudentiels COBAC/PARMEC
  - AgentDouanier     : Commerce international — TEC CEMAC/UEMOA, régimes douaniers, Incoterms 2020

Chaque agent hérite de AgentProBase → BaseAgent, pattern YukpoAssurance strict :
  - Fonctions de calcul déterministes au niveau module (standalone)
  - type_agent = TypeAgent.PRO_* (spécifique à chaque agent)
  - _necessite_validation() → False (agents consultatifs)
  - _prompt_questions_specifiques() implémenté

Routage _charger_agent_metier() dans routes_pro_agent.py :
  comptable/auditeur/fiscaliste           → AgentComptable
  drh/gestionnaire_rh                     → AgentDRH
  daf                                     → AgentDAF
  juriste/avocat/notaire                  → AgentJuriste
  banquier/analyste_credit/trader         → AgentBanquier
  ingenieur/architecte/chef_projet        → AgentIngenieur
  daa/data_analyst/data_scientist         → AgentDAA
  directeur_commercial/entrepreneur       → AgentCommercial
  charge_projets_ong/coordinateur_ong     → AgentONG
  responsable_microfinance/credit_officer → AgentMicrofinance
  transitaire/douanier/agent_transit      → AgentDouanier
  tous autres                             → AgentProBase (généraliste)
"""
