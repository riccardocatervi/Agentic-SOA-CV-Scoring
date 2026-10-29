# Learning log

## Sessione: sistema completo (agents, gateway MCP, client)

Costruito da Claude Code in autonomia su richiesta di Riccardo; la spiegazione dettagliata
arriva a sistema finito, per questo qui ci sono anche i punti da consolidare.

- Fatto: loop agentico scritto a mano, quattro agenti (JD Analyst, CV Matcher, Evaluator,
  Orchestrator), registry con allowlist dei tool, memory per job, gateway MCP su HTTP.
- Verificato solo con un modello finto che segue regole scritte a mano. Nessun modello vero
  provato: i problemi dei modelli piccoli (tool calling, JSON malformato) sono ancora ignoti.
- Da consolidare, in ordine: cos'è una tool call e perché la "memoria" dell'agente è la lista
  dei messaggi; cosa decide il codice e cosa decide l'LLM (score e verifica sono codice);
  perché i file passano per `cv_id`; come MCP separa agenti e servizi (`tools/list`, `tools/call`).
- Limiti da dichiarare nel report: gateway senza autenticazione, verifica fuzzy che può
  accettare un numero cambiato, coda in-process, nessun test su modello reale.
