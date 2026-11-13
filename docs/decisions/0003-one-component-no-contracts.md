# 0003. One component, no contracts

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha is a single component; nothing calls another component, but the domain has its own vocabulary.

## Decision

alpha turns interview answers into an enforced project (generate, adopt, update) and checks the answers, recipes, baselines and adoption steps that drive it. No calls, contract format none. Glossary: kit, area, component, recipe, principle, override, baseline, adoption step.

## Consequences

These eight terms are fixed names across code, docs and skills; a new concept needs a glossary entry. Splitting off a component would need contracts.
