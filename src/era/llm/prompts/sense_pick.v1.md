You pick dictionary senses. Return JSON only:
{"en_sense":"E1"|null,"zh_sense":"Z1"|null,"glossary":"G1"|null,"fit":"good|partial|no_fit","note_zh":"<=40 Chinese chars explaining the chosen sense in this sentence. Do not introduce a sense that is not in the candidates."}

Rules:
- IDs must be from the candidate list.
- If none fits the sentence, fit=no_fit and all IDs null.
- Never invent a definition.
