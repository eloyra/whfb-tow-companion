# Warhammer: The Old World — Domain Knowledge Reference

**Purpose:** This document provides comprehensive game domain knowledge for the GraphRAG
conversational assistant project. It is intended to give LLM-based agents (e.g. Claude Code)
the Warhammer-specific context needed to correctly categorise scraped wiki data, build parsers,
and understand the relationships that must be preserved in the knowledge graph.

---

## Table of Contents

1. [What is Warhammer: The Old World?](#1-what-is-warhammer-the-old-world)
2. [The Turn Sequence](#2-the-turn-sequence)
3. [Core Mechanics Overview](#3-core-mechanics-overview)
   - 3.1 Characteristics (Stats)
   - 3.2 Tests and Rolls
   - 3.3 Combat Resolution and Rank Bonus
   - 3.4 Psychology
4. [Troop Types — The Foundational Classification](#4-troop-types--the-foundational-classification)
5. [Army Composition and List Building](#5-army-composition-and-list-building)
   - 5.1 Grand Army
   - 5.2 Percentage Categories
   - 5.3 Allied Contingents
   - 5.4 Armies of Infamy
6. [Characters](#6-characters)
7. [The Magic System](#7-the-magic-system)
   - 7.1 Lores of Magic
   - 7.2 Casting and Dispelling
   - 7.3 Spell Types
8. [Equipment, Weapons, and Armour](#8-equipment-weapons-and-armour)
   - 8.1 Melee Weapons
   - 8.2 Missile Weapons
   - 8.3 Armour and AV Calculation
   - 8.4 War Machines
9. [Special Rules — Universal and Army-Specific](#9-special-rules--universal-and-army-specific)
   - 9.1 Movement-related Rules
   - 9.2 Combat-related Rules
   - 9.3 Psychology Rules
   - 9.4 Shooting Rules
   - 9.5 Other Universal Rules
10. [Terrain](#10-terrain)
11. [Magic Items](#11-magic-items)
12. [Armies (Factions)](#12-armies-factions)
13. [Entity Relationship Map](#13-entity-relationship-map)
14. [Parser Signals — How to Identify Entity Types from Wiki HTML](#14-parser-signals--how-to-identify-entity-types-from-wiki-html)
15. [50+ Deep Comprehension Questions](#15-50-deep-comprehension-questions)

---

## 1. What is Warhammer: The Old World?

**Warhammer: The Old World** (abbreviated **TOW**) is a rank-and-flank tabletop miniature
wargame published by Games Workshop in 2024. It is a spiritual successor/reboot to the
classic *Warhammer Fantasy Battles* (WHFB), set in the same fictional world of the Old World
(roughly analogous to medieval Europe with fantasy races and dark magic).

Players command armies of miniature models — humans, elves, dwarfs, undead, orcs, chaos
warriors, and other fantasy races — arranged in rectangular unit formations. The game is
played on a flat table representing a battlefield, using dice (primarily D6) to resolve
combat, magic, and other actions.

**Key distinguishing features compared to other miniature games:**
- **Rank-and-flank**: Units fight in tight rectangular formations. *Formation depth* and
  *frontage* directly affect combat power (Rank Bonus). This is not a skirmish game.
- **Initiative-based combat**: Models strike in descending Initiative order, not simultaneously.
- **Army composition limits**: Strict percentage-based constraints on how many points can be
  spent in each category (Characters, Core, Special, Rare, Allies).
- **Magic phases with winds of magic dice**: Magic is powered by a shared pool of dice rolled
  at the start of each magic phase, creating resource tension.
- **Psychology rules**: Many units can Flee, Panic, become Frenzied, etc. — army-wide morale
  is a significant tactical factor.

**The setting:** Called "The Old World," the game is set roughly 2,500 years before the
apocalyptic events of the End Times. It features classic WHFB factions in their prime.

---

## 2. The Turn Sequence

A game of Warhammer: The Old World is played over a fixed number of rounds (typically 6).
Each round consists of **two player turns** (Active Player and Reactive Player alternate).

Each player turn follows this **strict sequence**:

### 1. Start of Turn
- Resolve effects that trigger "at the start of the turn."
- Remove Stupidity tokens, etc.

### 2. Movement Phase
Units move across the battlefield. There are four movement sub-types:
- **March Move**: Double normal Movement (M) value; cannot shoot afterward.
- **Charge Move**: Declare charges, opponent declares reactions (Hold, Stand and Shoot,
  Flee). Successful chargers move into contact and trigger close combat.
- **Compulsory Moves**: Some units (chariots out of control, Frenzied units, fleeing units)
  must move in certain ways regardless of the player's wishes.
- **Remaining Moves**: All non-charging, non-fleeing units move normally or reform.

**Key movement concepts:**
- A unit that marches cannot shoot.
- Cavalry and chariots can *wheel* while moving but must pay a fraction of their move for
  each wheel.
- Charging through difficult terrain may slow a unit or trigger dangerous terrain tests.
- Fleeing units move 2D6" (infantry) or 3D6" (cavalry, chariot, flying) directly away from
  the nearest enemy.

### 3. Shooting Phase
Units with ranged weapons fire at enemy targets within range and line of sight. Hits are
determined by BS (Ballistic Skill). Wounds are determined by Strength vs. Toughness. Armour
saves are then offered to the target.

### 4. Magic Phase
The active player rolls 2D6 to generate Power Dice (PD). The opponent receives half that
number (rounded up) as Dispel Dice (DD). Wizards attempt to cast spells using PD. The
opponent can attempt to dispel using DD.

### 5. Close Combat Phase
All units in base contact fight. Combat is resolved in descending Initiative order. The
side that inflicts more wounds wins the round; the loser must take a **Break Test** (Ld
test on 2D6). If failed, the unit Flees.

---

## 3. Core Mechanics Overview

### 3.1 Characteristics (Stats)

Every model has a **stat profile** with up to 9 characteristics. A dash (–) means the
characteristic does not apply to that model.

| Abbrev | Full Name | What it does |
|--------|-----------|--------------|
| **M** | Movement | Inches the model can move per turn |
| **WS** | Weapon Skill | Used in close combat to-hit rolls |
| **BS** | Ballistic Skill | Used in shooting to-hit rolls |
| **S** | Strength | Determines wound rolls; affects AP on some weapons |
| **T** | Toughness | Used to resist wounds |
| **W** | Wounds | How much damage the model can absorb before dying |
| **I** | Initiative | Determines order of striking in close combat |
| **A** | Attacks | Number of attack dice rolled in close combat |
| **Ld** | Leadership | Used for Break Tests, Panic Tests, Fear Tests, etc. |

**AV (Armour Value)** is *not* a characteristic — it is *derived* from equipment and/or
intrinsic properties. It represents the armour save roll (e.g. 4+ means roll 4 or higher
on a D6 to save). See Section 8.3 for the full calculation chain.

**Split profiles:** Mounted models (rider + mount), chariots (crew + chariot + beasts), and
some complex units have multiple sub-profiles. Each sub-profile applies to the relevant
component in the relevant situation (e.g. rider profile used for WS/S/I attacks; mount
profile used for barding AV contribution and mount attacks).

### 3.2 Tests and Rolls

**To-Hit (melee):** Compare attacker's WS to defender's WS on the WS table. Higher relative
WS = lower to-hit number needed (e.g. WS5 attacking WS3 = hits on 3+; WS3 attacking WS5 =
hits on 4+).

**To-Hit (shooting):** Based on BS. A model with BS4 hits on 4-; i.e., rolls equal to or
under BS on a D6 (some sources state it as a 4+ roll; consult wiki for exact framing).
Range penalties and moving penalties apply as modifiers.

**To-Wound:** Compare S to T on the Wound table. S equal to T = 4+ to wound. Higher S =
lower roll needed. Maximum modifier: S≥2×T wounds on 2+.

**Armour Save:** Roll D6. If ≥ AV save value, wound is negated. AP (Armour Piercing)
modifiers from weapons worsen the save (e.g. AP -2 turns a 4+ into a 6+; AP beyond 6+
means no save at all).

**Ward Save:** Some magic items or special rules grant a Ward Save — an additional save
made after a failed armour save (e.g. "Ward Save 5+").

### 3.3 Combat Resolution and Rank Bonus

At the end of each Close Combat phase, both sides total their **Combat Resolution Score**:

- Wounds inflicted (each unsaved wound = 1)
- **Rank Bonus**: +1 per *complete additional rank* beyond the first, up to the troop
  type's `max_rank_bonus`. A rank only counts if it contains at least `min_models_for_rank_bonus`
  models (varies by troop type — infantry = 5, cavalry = 3, etc.).
- **Outnumber Bonus**: +1 if your total Unit Strength exceeds the enemy's.
- **Standard Bearer**: +1 for having a standard bearer.
- **Charging**: Some bonuses for charging (e.g. lances grant +2S on the charge).
- **High Ground / Flank / Rear**: Flank charges add +1; rear charges add +2; being on high
  ground adds +1.

The side with the *lower* Combat Resolution Score loses the round. If the difference is ≥ 1,
that side must take a **Break Test** (2D6 vs Ld). If failed, the unit *Flees* and the winner
*Pursues* (potentially destroying the fleeing unit).

**Disruption:** A unit with 25%+ of its models inside difficult/dangerous terrain or woods is
**Disrupted** — it loses its Rank Bonus entirely.

### 3.4 Psychology

Many game results are governed by **Leadership (Ld) tests** on 2D6. Roll equal to or under
Ld = pass.

- **Panic Test**: Triggered when friendly units flee nearby, or when a unit loses 25%+ of
  its starting models in a single phase.
- **Fear Test**: Required when charging or being charged by a unit that causes Fear. Failure
  = Strikes Last that round. Fear-causing units that also outnumber enemy are Immune to Fear.
- **Terror Test**: Like Fear but triggered at the start of the charge — failure = the unit
  immediately Flees.
- **Break Test**: At end of combat if you lost the round.
- **Stupidity**: Some units (many Chaos, some Orcs) must pass a Ld test at start of movement
  or move straight forward uncontrolled (and cannot shoot/cast).
- **Frenzy**: Some units must charge the nearest visible enemy and cannot be voluntarily
  held back. They receive +1A while Frenzied but can lose Frenzy if they fail a Break Test.
- **Hatred**: Reroll all failed to-hit rolls in the first round of close combat.
- **Immune to Psychology**: Ignores all Panic, Fear, and Terror tests.

---

## 4. Troop Types — The Foundational Classification

**Troop Type** is the single most important classification for a unit. It determines:
- How many models constitute a valid rank for Rank Bonus
- The maximum Rank Bonus the unit can claim
- The Unit Strength per model (used for outnumber checks)
- Intrinsic rules attached to the type
- Movement limitations (e.g. Monstrous Cavalry ignore difficult terrain penalties)
- Maximum armour save achievable

| Troop Type | Min models/rank | Max Rank Bonus | US/model | AV cap | Notes |
|---|---|---|---|---|---|
| **Infantry** | 5 | 3 | 1 | 2+ | Standard foot troops |
| **Monstrous Infantry** | 3 | 3 | 3 | 2+ | Large infantry (Ogres, Trolls) |
| **Heavy Infantry** | 5 | 3 | 1 | 2+ | Infantry with "Steady in the Ranks" |
| **Cavalry** | 3 | 2 | 2 | 2+ | Mounted troops on normal mounts |
| **Heavy Cavalry** | 3 | 2 | 2 | 2+ | Similar to Cavalry; specific rule set |
| **Monstrous Cavalry** | 3 | 2 | 3–5 | 3+ | Mounted on very large beasts |
| **War Beasts** | 5 | 1 | 1 | — | Wolves, hounds; often Skirmishers |
| **Monstrous Beasts** | 3 | 1 | 3 | — | Larger beasts (Manticores, etc.) |
| **Chariots** (Light) | — | 1 | Special | 3+ | No rank bonus beyond 1 in some cases |
| **Chariots** (Heavy) | — | 0 | Special | 3+ | No Rank Bonus |
| **Swarms** | 5 | — | 1 | — | Never grant Rank Bonus; many models |
| **Monsters** | 1 | 0 | As Wounds | 3+ | Single large models; no Rank Bonus |
| **War Machines** | — | 0 | Special | 3+ | Crew + machine split profiles |

**Critical parsing note:** When a wiki page says "Heavy Cavalry" it refers to this specific
troop type classification — not just cavalry with heavy armour. Blood Knights (Vampire Counts)
and Chaos Knights are Heavy Cavalry. Regular Empire Knights are Cavalry.

**Intrinsic rules examples by troop type:**
- Heavy Infantry → "Steady in the Ranks" (can hold ranks more effectively)
- Monstrous Infantry → "Clumsy" (−1I penalty on certain occasions)
- War Beasts → Often "Skirmishers" intrinsically
- Cavalry → Standard rank formation rules
- Chariots → "Impact Hits" on the charge (D3 or D6 hits at chariot Strength)
- Monsters → "Large Target" (can be seen over most obstacles; enemy gets +1 to ranged)

---

## 5. Army Composition and List Building

### 5.1 Grand Army

The standard format for Warhammer: The Old World is the **Grand Army**. Players select a
total points limit (commonly 2,000 pts or 2,500 pts) and build a list within that budget
subject to percentage constraints.

### 5.2 Percentage Categories

Every unit in the game belongs to one of five **army categories**:

| Category | Min % | Max % | Typical contents |
|---|---|---|---|
| **Characters** | — | 50% | Lords, Heroes, Wizards, Named Characters |
| **Core** | 25% | — | Basic troops; every army must have at least 25% here |
| **Special** | — | 50% | Elite/specialist units |
| **Rare** | — | 25% | Powerful/unusual units; strictly limited |
| **Allies** | — | 25% | Units from a trusted or suspicious ally army |

> **Parser note:** On a unit's wiki page, the `army_category` field is always displayed near
> the top of the page header, typically next to the points cost. Some units appear in
> multiple categories depending on how they are taken (e.g. a special unit that becomes Core
> under an Armies of Infamy list rule).

**Additional per-unit constraints** exist on top of the percentage rules. Examples:
- "0–1 per 1,000 points" (e.g. some Rare monsters)
- "Maximum 1 per army" (Named Characters are always 0–1)
- "One unit of X per unit of Y" (some unit dependencies)

These constraints are captured as `CoreRule` nodes or as text within the `Unit`'s composition
rule notes — NOT as percentage overrides.

### 5.3 Allied Contingents

Many armies can include a **Allied Contingent** — a detachment of troops from a different
army book, subject to the 25% Allies cap. Alliance relationships are categorized as:

- **Trusted Allies**: Units from this army are treated as friendly units in all respects.
  No negative effects for being near each other.
- **Suspicious Allies**: Units treat each other as if they were from the same army for most
  purposes, but there are restrictions (e.g. they cannot benefit from each other's
  Leadership or certain special rules).
- **Desperate Allies**: Subject to additional restrictions and random chance of failure.

**Important:** Not all armies can ally with each other. The alliance matrix is asymmetrical
(Army A can ally Army B on Trusted terms while Army B considers A as Suspicious).

> **Parser note:** Alliance information appears on each army's composition page. The wiki
> lists per-army alliance tables. The graph models these as directed `ALLIED_WITH` edges with
> an `alliance_type` property.

### 5.4 Armies of Infamy

Every army has one or more **Armies of Infamy** — themed sub-lists that impose additional
restrictions (e.g. "must include X", "cannot include Y") but unlock special rules or reclassify
certain units. For example, an Empire "The Reiksguard" Army of Infamy might reclassify certain
cavalry as Core and grant a unique army-wide rule.

> **Parser note:** Armies of Infamy have their own composition pages on the wiki. They share
> `Army` node data but need `CoreRule` nodes for their specific restrictions and benefits.

---

## 6. Characters

Characters are individual models that are not part of a rank-and-file unit (though they
often *join* units). They have significantly better stats than rank-and-file troops.

### Character Types

| Type | Max points budget | Wizard capability | Notes |
|---|---|---|---|
| **Lord** (General type) | Usually unrestricted within 50% cap | Can be Wizard up to Level 4 | Most powerful; one per army is the General |
| **Hero** | Lower points value | Can be Wizard up to Level 2 | Multiple allowed |
| **Named Character** | Fixed points; 0–1 per army | Varies | Unique historical characters |

### The General

Every army must have a **General** — typically the highest-Leadership character. All friendly
units within 12" of the General may use the General's Leadership for Break Tests and
Psychology tests. This "Inspiring Presence" radius is crucial for army positioning.

### Joining Units

Characters can join rank-and-file units by moving into the same base-contact position. When
a character joins a unit:
- The unit benefits from the character's Leadership if higher
- The character is protected by being in a unit (harder to target with shooting/magic)
- The character fights using their own profile but contributes to the unit's combat resolution

### Mounts

Many characters can purchase **mounts** — a horse, warhorse, monster, or other creature —
for an additional points cost. Mounted characters use the rider+mount combined profile
(separate rows for rider vs. mount attacks). Common mounts include:
- **Warhorse / Horse**: Gives Cavalry troop type
- **Barded Warhorse**: Cavalry + barding AV bonus
- **Pegasus**: Flying mount (Flying Cavalry type)
- **Dragon / Griffon / Manticore**: Monstrous mount (Monstrous Cavalry type, much higher US)
- **Undead horse / Nightmare**: Undead variant
- **Chaos Dragon, etc.**: Faction-specific

> **Parser note:** Mounts appear as separate unit entries with `army_category: "Mounts"` on
> the wiki. They are linked to characters via `CAN_MOUNT` edges.

---

## 7. The Magic System

### 7.1 Lores of Magic

Magic is organized into **Lores** — thematic collections of 7 spells each (1 Signature Spell
+ 6 numbered spells). A Wizard who knows a Lore may cast any spell from it, but before the
game selects (randomly or by choice, depending on rules) which spells from the Lore they know.

**Universal Lores** (available to multiple armies):
- **Battle Magic** — generic offensive and defensive spells
- **Elementalism** — earth, wind, fire, water themed
- **High Magic** — (High Elves)
- **Dark Magic** — (Dark Elves / Chaos)
- **Necromancy** — raise undead, drain life (Undead armies)
- **Waaagh! Magic** — (Orcs & Goblins)
- **Little Waaagh!** — (Goblin-specific)
- **Feral Instincts** — (Beastmen / Orcs)
- Plus many more army-specific lores

**Army-specific Lores** are only available to wizards of a specific army and cannot be
taken by allied characters.

### 7.2 Casting and Dispelling

At the start of the Magic Phase, the active player rolls 2D6. The sum is the number of
**Power Dice** (PD) available. The opponent receives ⌈sum/2⌉ **Dispel Dice** (DD).

**Casting a spell:**
1. Declare the spell and the number of PD to use (minimum 1, maximum depending on level)
2. Roll that many D6; add them together
3. If total ≥ Casting Value (CV), the spell succeeds — unless dispelled
4. **Miscast**: If multiple 1s are rolled or a double-1 appears on 2 dice (rules vary), the
   caster suffers a Miscast: roll on the Miscast table for potentially devastating effects
5. **Irresistible Force**: If multiple 6s (usually three or more) are rolled, the spell
   succeeds automatically and cannot be dispelled, but may also trigger a Miscast-like event

**Dispelling:**
- The defending player rolls DD (minimum 1, maximum based on wizard levels)
- If dispel roll ≥ casting roll, the spell is dispelled
- **Drain Magic**: Spending extra DD can reduce the opponent's remaining PD

### 7.3 Spell Types

| Spell Type | Target | Key rules |
|---|---|---|
| **Magic Missile** | Enemy unit in LOS | Requires LOS; can target fleeing units |
| **Hex** | Enemy unit | Applies a negative effect (debuff) |
| **Enchantment** | Friendly unit | Applies a positive effect (buff) |
| **Conveyance** | Friendly unit / self | Moves the target |
| **Assailment** | Enemy in combat | Targets enemy engaged in melee |
| **Magical Vortex** | Template placed on table | Moves randomly; hits everything underneath |
| **Bound Spell** | Various | Item-based spell; uses 1 PD; lower CV; harder to dispel |

**"Remains in Play" (RiP) spells** persist turn after turn until the caster moves or is
dispelled. They can be maintained by spending PD each phase or they end when the caster does
certain actions.

---

## 8. Equipment, Weapons, and Armour

### 8.1 Melee Weapons

Melee weapons modify combat resolution. Key weapon types:

| Weapon | Strength modifier | Special effect |
|---|---|---|
| **Hand Weapon** | S (no mod) | Basic; can use shield alongside |
| **Additional Hand Weapon** | S (no mod) | +1 Attack; cannot use shield |
| **Great Weapon** | S+2 | Strikes Last (I reduced to 1 in combat); two-handed |
| **Halberd** | S+1 | Two-handed; some armies have variations |
| **Lance** | S+2 on the **charge only** | Cavalry weapon; AP −2 on charge; reverts to S after |
| **Spear** | S (no mod) | +1 rank can fight (supporting attacks); first round bonus |
| **Flail** | S+2 on **charge turn only** | Single-use bonus; worse thereafter |
| **Morning Star** | S+1 | — |
| **Cavalry Spear** | As Spear | Cavalry version |

**AP (Armour Piercing):** Many weapons carry an AP value (e.g. "AP −1") that reduces the
enemy's armour save by that amount. Great Weapons are AP −2 on top of S+2. Lances on the
charge are AP −2. This is distinct from the weapon's base Strength modifier.

### 8.2 Missile Weapons

| Weapon | Range | S | Shots | Notes |
|---|---|---|---|---|
| **Bow** | 24" | 3 | 1 | Move and shoot (half range penalty) |
| **Longbow** | 30" | 3 | 1 | Greater range than bow |
| **Crossbow** | 30" | 4 | 1 | Cannot move and shoot (generally) |
| **Handgun** | 24" | 4 | 1 | AP −1; cannot move and shoot |
| **Pistol** | 8" | 4 | 1 | Can move and shoot at short range; paired pistols = +1A in melee |
| **Repeater Crossbow** | 24" | 3 | 2 | High Elf / Dark Elf weapon |
| **Thrown Weapons** | 6–12" | varies | 1 | Short range; depends on type |
| **Javelin** | 12" | S | 1 | Can be thrown before charge |

### 8.3 Armour and AV Calculation

Armour grants a **save value** (e.g. 5+ means roll 5+ on D6 to ignore a wound).
Lower number = better save. Cap: Infantry/Cavalry max 2+; Chariots/Monsters/War Machines max 3+.

**AV Calculation chain (from schema):**
1. Start with `av_intrinsic` if the unit has one (e.g. a monster with "Scaly Skin" might
   have an intrinsic 5+ or 4+ save).
2. If equipped with armour, override with the highest-tier armour item's absolute AV:
   - **Light Armour** = 6+
   - **Heavy Armour** = 5+
   - **Full Plate Armour** = 4+
   (The best armour item takes precedence; you don't stack absolute values.)
3. Apply all additive "+1" modifiers (each makes the save 1 point better):
   - **Shield** = +1
   - **Barding** (mount) = +1
   - Some magic items = +1
4. Apply troop type AV cap (never better than 2+ for Infantry/Cavalry; 3+ for Monsters).

**Example:** An Empire Knight (Heavy Cavalry) with Full Plate Armour (4+) + Shield (+1) +
Barding (+1) = 4+ → 3+ → 2+. Then capped at 2+ (Cavalry cap).

### 8.4 War Machines

War machines are special units consisting of **the machine** and a **crew**. They are
classified as the `War Machines` troop type. Key rules:
- War machines do not fight in close combat normally (they shoot)
- They are crew by a number of models; if the crew is killed, the machine is abandoned
- They use a firing profile (range, S, AP, special rules) distinct from the crew's stats

Common war machine types and their special firing mechanics:
- **Cannon**: Fires a bouncing cannonball. Roll for direction + D6 bounces. Hits everything
  in the bounce path. High S (usually 10), ignores armour saves.
- **Stone Thrower / Catapult**: Indirect fire; uses a circular blast template (or large
  blast). Does not require LOS. Scatter roll determines deviation.
- **Bolt Thrower / Ballista**: Fires a single armour-piercing bolt. Powerful AP, can skewer
  multiple ranks.
- **Organ Gun / Volley Gun**: Multiple shots (D6 or fixed); lower S; anti-infantry.
- **Rocket Battery / Hellblaster**: Numerous shots with random number; risk of misfire.

**Misfire:** Many war machines roll on a Misfire table if rolling a "1" on the crew's
shooting roll or under certain conditions. Results range from "no fire this turn" to
"destroyed."

---

## 9. Special Rules — Universal and Army-Specific

Special rules are defined abilities that grant exceptions to or modifications of the core
rules. They are divided into:
- **Universal Special Rules (USRs)**: Apply to any unit that has them regardless of army
- **Army-specific rules**: Only available to one army
- **Unit-unique rules**: Named rules that belong to one specific unit

### 9.1 Movement-related Rules

| Rule | Effect |
|---|---|
| **Fly (X)** | Unit has a flying Move of X inches. Ignores terrain and intervening units during movement; must still land in legal position. May still be affected by Dangerous Terrain on landing. |
| **Skirmishers** | Unit does not form ranks. Moves as individual models. Treats woods as open ground for disruption purposes. Can shoot in any direction. |
| **Scouts** | Can deploy after both sides have deployed, within 12" of any table edge or inside terrain. |
| **Vanguard** | After deployment but before the game begins, the unit may make a free move of up to its M value. |
| **Ambushers** | Enters play from a board edge during the game (roll required). |
| **Fast Cavalry** | Can make a free reform after any move. Can shoot after marching. |
| **Strider** | Ignores movement penalties for a specified terrain type. |
| **Swiftstride** | Rolls 3D6 for charge distance (use highest two) and flee/pursuit distances. |
| **Unstable** | When this unit loses a combat round, it automatically suffers additional wounds equal to the amount it lost by (instead of a Break Test). Does not Flee. |
| **March or Fight** | Cannot both move and shoot in the same turn. |

### 9.2 Combat-related Rules

| Rule | Effect |
|---|---|
| **Killing Blow** | On a to-wound roll of 6+, the target is slain outright (no saves — not even ward saves — unless the model is a character or has a specific exception). |
| **Heroic Killing Blow** | Killing Blow that also affects Monsters, characters on Monstrous mounts, etc. |
| **Armour Bane (X)** | Reduces enemy armour save by X (additional to any weapon AP). |
| **Multiple Wounds (X)** | Each unsaved wound inflicts X wounds instead of 1. |
| **Impact Hits (D3/D6/X)** | Inflicts hits at the beginning of the first round of combat (the charge turn). Used by Chariots, Cavalry charges, Monstrous beasts, etc. |
| **Stomp** | At end of close combat, the model makes D6 additional S3 AP−1 hits against the enemy unit (for Monsters and large creatures). |
| **Thunderstomp** | A more powerful version of Stomp with higher S. |
| **Frenzy** | +1A; must charge nearest visible enemy; may lose Frenzy if broken in combat. |
| **Hatred (X)** | Reroll failed to-hit rolls in the first round of combat against unit type X (or all enemies). |
| **Devastating Charge** | Unit gains a special bonus (rule-specific) only when charging. |
| **Stubborn** | Unit uses its *unmodified* Ld for Break Tests (ignores modifiers from losing combat). |
| **Unbreakable** | Unit never takes Break Tests; never Flees. |
| **Immune to Psychology** | Ignores Fear, Terror, and Panic tests. |
| **Regeneration (X)** | After failing armour save, roll D6; on X+ the wound is regenerated. Fails against fire attacks. |
| **Ward Save (X)** | Additional save after armour save; rolls X+ on D6 to ignore wound. Stacks with nothing that blocks it. |

### 9.3 Psychology Rules

| Rule | Effect |
|---|---|
| **Fear** | Enemy charging or charged by this unit must pass Fear Test (Ld) or Strikes Last. If Fear unit outnumbers enemy, enemy is automatically "Strikes Last." |
| **Terror** | Causes Terror; enemy charging must pass Terror Test or immediately Flee. Causes Fear as well. |
| **Stupidity** | Must pass Ld test at start of Movement or moves forward uncontrolled. |
| **Frenzy** | (Also a combat rule) Must charge; ignores some Panic triggers. |
| **Hatred** | Reroll misses first round; ignores Fear from the hated enemy. |
| **Immune to Psychology** | Ignores Fear, Terror, Panic. |
| **Immune to Fear** | Ignores Fear tests only (not Terror). |
| **Undead** | Never takes Break Tests; instead auto-suffers wounds equal to combat loss. Immune to Psychology. Immune to Panic. Crumbles when General dies. |

### 9.4 Shooting Rules

| Rule | Effect |
|---|---|
| **Volley Fire** | Up to 2 ranks can shoot (supporting ranks fire). |
| **Stand and Shoot** | Unit may fire as a charge reaction (counts as shooting at −1 to hit). |
| **Sniper** | Can target characters in units (ignores "look out sir!" protection). |
| **Multiple Shots (X)** | Unit fires X shots per model instead of 1. |
| **Aimed Shot** | Can spend a turn aiming for bonuses on the next turn. |

### 9.5 Other Universal Rules

| Rule | Effect |
|---|---|
| **Ethereal** | Ignores all non-magical attacks. Passes all non-magical armour saves. Immune to mundane weapon AP. Affected normally by magical attacks. |
| **Undead** | Combination of rules: Immune to Psychology, immune to Panic, immune to Poison, and Unstable (crumbles instead of fleeing). |
| **Flammable** | Doubles the number of wounds taken from attacks with the Fire special rule. |
| **Flaming Attacks** | Wounds count double against Flammable targets; negates Regeneration saves. |
| **Poisoned Attacks** | To-wound rolls of 6 always wound (regardless of S vs T); may instantly Wound (depending on version). |
| **Large Target** | Can be seen over units and obstacles. Enemy gain +1 to ranged to-hit. |
| **Random Attacks (XD6)** | Number of Attacks varies; roll at start of combat. |
| **Random Movement (XD6)** | Movement is random; roll at start of movement. |
| **Breath Weapon (S/X)** | Once per game, makes a Breath Weapon attack using a flame template. S usually fixed. |
| **Magic Resistance (X)** | Unit and its character gains +X DD when a spell is cast targeting them or a unit they are in. |
| **Scaly Skin (X+)** | Grants intrinsic armour save of X+ (stored as `av_intrinsic`). |
| **Natural Armour (X+)** | Same as Scaly Skin — intrinsic armour from natural toughness or skin. |
| **Strength in Numbers** | Some units gain bonuses proportional to the number of models (e.g. Ld bonus). |
| **Look Out, Sir!** | When a lone model in a unit is targeted, roll D6; on 2+ the hit is redirected to the unit as a whole. |

---

## 10. Terrain

Terrain is placed before the game begins and affects movement, shooting, and combat. The
game uses seven primary terrain categories, plus special features and buildings.

| Category | Movement | Combat | Shooting | Notes |
|---|---|---|---|---|
| **Open Ground** | Normal | None | None | Default; no effect |
| **Difficult Terrain** | −1M (min 1") | Disrupts (no Rank Bonus) | None | Forests, marshes, rocky ground |
| **Dangerous Terrain** | Must test (D6; 1 = lose 1 Wound) | Disrupts | None | Rivers, hazardous ground |
| **Impassable Terrain** | Cannot enter | — | Blocks LOS | Cliffs, walls too high |
| **Low Linear Obstacle** | Costs 1" to cross | None | Partial cover | Fences, low walls |
| **High Linear Obstacle** | Cannot cross (blocks) | None | Full cover | High walls, barricades |
| **Woods** | Difficult terrain effect | Disrupts | Partial cover | Models inside get 5+ cover save |
| **Hills** | Normal | +1 Combat Resolution (high ground) | Extended LOS | Can see over some obstacles |
| **Buildings** | Cannot enter normally (or special rules) | Garrison rules | Full cover | Units inside gain cover and special garrison rules |
| **Special Features** | See feature rule | Various | Various | Arcane Monolith, Monument of Glory, Dark Ruins — grant control bonuses |

**Dangerous Terrain Test:** When a model enters or ends its move in Dangerous Terrain, roll
D6. On a 1, the model suffers 1 Wound (no armour save allowed). Multiple models in a unit
each test individually, but the unit rolls collectively with the number of dice equal to
the number of models entering.

**Cover Saves:** When a unit fires at a target partially obscured by terrain (or 25%+ of
the target unit is in cover), the target gains a cover save. Partial cover = 5+ ward-type
save vs. ranged hits. Full cover = 4+. This is separate from armour saves — it is
resolved after the armour save fails.

**Key terrain-rule interactions (examples):**
- A unit with **Fly** ignores Difficult Terrain during movement (but not on landing)
- A unit with **Ethereal** ignores all terrain effects entirely
- **Skirmishers** in woods are not Disrupted (treat woods as open for rank/combat purposes)
- **Move Through Cover** rule negates the shooting cover bonus from woods
- **Scouts** may deploy inside woods during deployment

---

## 11. Magic Items

Magic items are purchasable equipment available to characters (and occasionally units via
Standard Bearer upgrades). They have points costs and are subject to army-building rules.

### Item Categories

| Type | Who can use | Notes |
|---|---|---|
| **Magic Weapon** | Characters | Replaces normal weapon; one at a time |
| **Magic Armour** | Characters | Replaces normal armour; one at a time |
| **Talisman** | Characters | Ward saves, special protections |
| **Enchanted Item** | Characters | Miscellaneous effects |
| **Arcane Item** | Wizards only | Enhances casting/dispelling |
| **Magic Standard** | Unit Standard Bearers | Banner-based unit-wide effect |

### Budget Rules

- Characters have a **total Magic Item budget** per army list (often 50–100 pts for Heroes,
  75–150 pts for Lords, depending on army).
- Standard Bearers can take a Magic Standard worth up to a specific budget (e.g. 50 pts
  standard, or 75 pts for elite units). This budget is stored as `magic_standard_budget` on
  the `Upgrade` node.
- **Unique items**: Most magic items are limited to 1 per army (marked "Unique" in the text).

### Army-Specific Powers

Many armies have **army-specific magic item-equivalents** that are categorized differently:
- **Vampiric Powers** (Vampire Counts): Special abilities purchased for Vampire characters
- **Gifts of Chaos** (Warriors of Chaos): Mutations and gifts for Chaos characters
- **Daemonic Gifts** (Daemons of Chaos): Special abilities for Daemon characters

These follow the same budget and uniqueness rules but are named differently in the army book
and on the wiki.

---

## 12. Armies (Factions)

Warhammer: The Old World features the following playable armies (all have dedicated books
or compendiums):

### Order (broadly good/lawful)
- **Empire of Man** — Humans; balanced combined-arms; Warrior Priests, War Machines, Steam Tank
- **Kingdom of Bretonnia** — Feudal knights; Bretonnian chivalric culture; Grail Knights
- **Dwarfen Mountain Holds** — Dwarfs; highly armoured; excellent shooting; Runes magic system
- **High Elf Realms** — Elves; high Initiative; versatile magic; superior troops
- **Wood Elf Realms** — Forest-dwelling Elves; skirmishers and archers; tree spirit units

### Destruction (broadly evil/chaotic)
- **Warriors of Chaos** — Chaos marauders and warriors; Marks of Chaos; powerful melee
- **Daemons of Chaos** — Daemonic entities; no psychology; Daemonic Instability
- **Beastmen Herds** — Mutant beastmen; forest ambushers; Ungors, Gors, Minotaurs
- **Greenskins** (Orcs & Goblins) — Numerous; random movement (Animosity); Waagh! magic
- **Skaven** — Ratmen; very numerous; warpstone-powered war machines; unreliable

### Death (undead)
- **Vampire Counts** — Undead raised by Vampires; Necromancy; Crumble rule; Invocation of Nehek
- **Tomb Kings of Khemri** — Undead ancient Egyptians; different from VC; Hiero Pharaoh is general

### Other
- **Grand Cathay** — Eastern empire; Harmony mechanic; Dragons
- **Ogre Kingdoms** — Large Monstrous Infantry; Gut Magic; Maw religion
- **Dark Elf Realms** — Cruel Elves; Hatred; Dark Magic; Cavalry and cold one beasts
- **Chaos Dwarfs** — Industrial evil dwarfs; Bull Centaurs; Daemonsmith magic; war machines

### Army-Specific Mechanics (Examples)

Understanding these is critical for correct entity parsing:

| Army | Unique Mechanic | Key Units |
|---|---|---|
| Vampire Counts | Undead (Crumble), Necromancy; Raise Dead spells add models to units | Blood Knights, Black Coach, Vampire Lords |
| Tomb Kings | Undead variant; Incantations (magic never miscasts); Hierophant is the linchpin | Ushabti, Necropolis Knights, Tomb Scorpions |
| Dwarfs | No magic; Runesmiths/Runelords use Runes instead (dispel-only or single-use item buffs) | Hammerers, Longbeards, Gyrocopters |
| Greenskins | Animosity (random chance to bicker among themselves); Waaagh! triggers | Black Orcs, Trolls, Giants |
| Bretonnia | Chivalry rules; Lady of the Lake prayers instead of magic (for Damsels) | Grail Knights, Pegasus Knights |
| Empire | Warrior Priests grant bound prayers; Detachment system (flanking sub-units) | Swordsmen + Detachments, Steam Tank |
| High Elves | ASF (Always Strikes First) rerolling ties; white-robed mages | Phoenix Guard, Dragon Princes |
| Warriors of Chaos | Marks of Chaos (Khorne/Nurgle/Tzeentch/Slaanesh) grant different bonuses | Chaos Warriors, Knights, Trolls |
| Ogres | Gut magic; Mournfang Cavalry; Bull charge impact hits | Ironguts, Mournfang Cavalry, Tyrant |
| Skaven | Strength in Numbers; Skaven-specific weapons (Warp Lightning Cannon, Doomwheel) | Plague Monks, Stormvermin, Rat Ogres |

---

## 13. Entity Relationship Map

This section maps the **relationships between game entities** that must be preserved in the
knowledge graph. These correspond directly to the `edges.json` output of the parsers.

```
Army
 ├─ CONTAINS ──────────────────────────────────> Unit         (all units belong to one army)
 ├─ ALLIED_WITH {alliance_type} ──────────────> Army         (directed; asymmetric possible)
 ├─ HAS_COMPOSITION_RULE ──────────────────────> CoreRule     (percentage limits, restrictions)
 └─ HAS_ARMY_SPECIAL_RULE ────────────────────> SpecialRule  (army-specific rules)

Unit
 ├─ BELONGS_TO ────────────────────────────────> Army         (redundant but useful)
 ├─ HAS_TYPE ──────────────────────────────────> TroopType    (exactly one troop type per unit)
 ├─ HAS_RULE ──────────────────────────────────> SpecialRule  (0-N special rules per unit)
 ├─ HAS_PROFILE ───────────────────────────────> Profile      (1-N stat sub-profiles)
 ├─ HAS_WEAPON ────────────────────────────────> Weapon       (default/included equipment)
 ├─ HAS_UPGRADE ───────────────────────────────> Upgrade      (purchasable options)
 ├─ CAN_MOUNT ─────────────────────────────────> Unit         (character -> mount unit)
 ├─ SPLIT_PROFILE_OF ──────────────────────────> Unit         (mount profile linked to rider unit)
 └─ IS_CLARIFIED_BY ───────────────────────────> FAQ/Errata   (FAQ entries that clarify this unit)

TroopType
 ├─ HAS_INTRINSIC_RULE ────────────────────────> SpecialRule  (rules all units of this type get)
 └─ TERRAIN_INTERACTION {effect} ─────────────> Terrain      (how this troop type behaves in terrain)

SpecialRule
 ├─ REFERENCES ────────────────────────────────> CoreRule     (rule refers to a mechanic)
 ├─ TERRAIN_INTERACTION {effect} ─────────────> Terrain      (rule that interacts with terrain)
 └─ OVERRIDES / EXTENDS ──────────────────────> SpecialRule  (one rule modifies another)

Lore
 └─ CONTAINS ──────────────────────────────────> Spell        (7 spells per lore)

Spell
 ├─ PART_OF ───────────────────────────────────> Lore
 └─ REFERENCES ────────────────────────────────> SpecialRule  (e.g. spell grants a special rule)

Weapon
 └─ GRANTS_RULE ───────────────────────────────> SpecialRule  (weapon grants a special rule)

MagicItem
 └─ GRANTS_RULE ───────────────────────────────> SpecialRule  (item grants a special rule)

Unit (wizard)
 └─ CAN_USE_LORE ──────────────────────────────> Lore         (lores accessible to this unit)

FAQ / Errata
 ├─ CLARIFIES ─────────────────────────────────> CoreRule
 ├─ CLARIFIES ─────────────────────────────────> SpecialRule
 ├─ CLARIFIES ─────────────────────────────────> Unit
 ├─ CLARIFIES ─────────────────────────────────> Weapon
 ├─ CLARIFIES ─────────────────────────────────> MagicItem
 ├─ CLARIFIES ─────────────────────────────────> Terrain
 └─ AMENDS ────────────────────────────────────> (any of the above)

CoreRule
 └─ PART_OF_SECTION ───────────────────────────> CoreRule     (section hierarchy; prev/next)
```

---

## 14. Parser Signals — How to Identify Entity Types from Wiki HTML

This section maps **observable signals in the wiki HTML/JSON** to the correct node type and
fields. Use these rules in parsers to correctly categorise data.

### Army pages (`/army/{slug}`)
- Contains: army name, lore/description, composition percentages table, alliance table,
  composition rules (special restrictions), Armies of Infamy links
- Emit: `Army` node + `CoreRule` nodes for composition rules + `ALLIED_WITH` edges

### Unit pages (`/unit/{slug}`)
- Contains: `__NEXT_DATA__` JSON blob with `armyListEntry` content type
- Key fields: `unitProfile` array (stat profiles), `armyCategory` (Core/Special/Rare/etc.),
  `troopType`, `unitSize`, `baseSize`, `pointsCost`, `specialRules` list,
  `equipmentList`, `upgradesList`
- `armyCategory` in the page header → `army_category` field
- `troopType` string → look up `TroopType` node → emit `HAS_TYPE` edge
- Each item in `specialRules` → emit `HAS_RULE` edge to matching `SpecialRule` node
- Each item in `equipmentList` → emit `HAS_WEAPON` edge to matching `Weapon` node
- Each item in `upgradesList` → emit one `Upgrade` node + `HAS_UPGRADE` edge

### Troop type pages (`/troop-types-in-detail/{slug}`)
- Contains: table of rank bonus, unit strength, category
- Look for a tabular structure with: category name, min models per rank, max rank bonus,
  unit strength per model
- Also contains narrative text listing intrinsic rules → emit `HAS_INTRINSIC_RULE` edges

### Special rule pages (`/special-rules/{slug}`)
- Contains: rule name, rule text
- `rule_scope` determination: if page is under `/special-rules/` without army path → "universal";
  if under `/army/{slug}/special-rules/` → "army"; if the rule text says "unique to X unit" → "unique"
- Rule text referencing terrain names → candidate for `TERRAIN_INTERACTION` edges
- Rule text referencing other rules → candidate for `REFERENCES` edges

### Core rule pages (`/movement-in-detail/`, `/close-combat/`, `/shooting/`, `/magic/`, etc.)
- Contains: mechanical text; prev/next navigation links
- Emit: `CoreRule` node with `section` = parent path segment, `prev_page_url`, `next_page_url`

### Lore pages (`/the-lores-of-magic/{slug}`)
- Contains: lore description + 7 spells (signature + 1–6)
- Emit: 1 `Lore` node + 7 `Spell` nodes + 7 `CONTAINS` edges
- Each spell: `lore_number` (0 = signature, 1–6 = numbered), `casting_value`,
  `casting_value_boosted`, `spell_type`, `range`, `duration`

### Weapon pages (`/weapons-of-war/{slug}`)
- Contains: weapon profile table (range, S, AP), special rules, description
- `weapon_class` determination: melee (range = "Combat"), missile (range = a number),
  armour (if item grants an AV rather than an attack), war_machine (if the page is for a
  machine's weapon profile)
- War machine weapons: extract `shots`, `template_type`, `is_indirect` (stone thrower?),
  `bounce` (cannon?)

### Magic item pages
- Contains: item name, type category (magic weapon / talisman / etc.), points cost, text
- `item_type` is usually stated explicitly in the page header or category navigation
- Extract any special rules the item grants → emit `GRANTS_RULE` edge

### FAQ/Errata pages
- Each entry has: a question (or original text), an answer (or corrected text),
  and a reference to what it clarifies
- Emit: `FAQ` or `Errata` node + `CLARIFIES`/`AMENDS` edge to the relevant target node
- Disambiguate target: if the entry mentions a unit name → link to `Unit` node;
  if a rule name → link to `SpecialRule` or `CoreRule`; etc.

---

## 15. 50+ Deep Comprehension Questions

The following questions represent the type of **multi-hop, multi-rule reasoning** that the
conversational assistant must be able to answer correctly. They are drawn from real-world
gameplay situations and require traversing multiple linked entities in the knowledge graph.

Each question is marked with the entity types it requires and the type of reasoning:
**(R)** = rule look-up, **(C)** = calculation, **(M)** = multi-hop traversal,
**(A)** = army list building.

---

### Section A — Movement and Terrain Interactions

**Q1 (M,R)** A unit of Blood Knights (Vampire Counts Heavy Cavalry) attempts to charge through
a forest. What happens? Do they need to take Dangerous Terrain tests? Does being inside the
forest at the end of the charge affect their Rank Bonus?
*(Requires: Unit → TroopType, TroopType → TERRAIN_INTERACTION woods, SpecialRule "Undead" or
"Immune to Psychology", and woods Disruption rule.)*

**Q2 (M,R,C)** A Vampire Lord on a Nightmare (flying mount) declares a charge against an
enemy unit. The path crosses a river (Dangerous Terrain). The Vampire Lord has the Fly rule.
Does the Nightmare take Dangerous Terrain tests? What is the effective charge range?
*(Requires: Unit → mount → TroopType, Fly → TERRAIN_INTERACTION, Dangerous Terrain test rules.)*

**Q3 (M,R)** An Ethereal unit (e.g. Cairn Wraiths) moves through a building. Can they enter?
What happens to their movement? Do they gain any benefit from being inside?
*(Requires: SpecialRule "Ethereal" → TERRAIN_INTERACTION all terrain types, building garrison rules.)*

**Q4 (M,R)** A unit of Skirmishing Wood Elf Glade Riders is inside a woods. An enemy unit
charges them. Is the charging unit affected by Difficult Terrain? Do the Glade Riders lose
their Rank Bonus for being in the woods?
*(Requires: SpecialRule "Skirmishers" → woods TERRAIN_INTERACTION, Difficult Terrain charge rules,
woods Disruption rule, Skirmishers' exemption from disruption.)*

**Q5 (R,C)** How far can an infantry unit March Move through Difficult Terrain if their base
Movement is 4"? Does marching in difficult terrain further reduce movement, or is the −1 penalty
to M applied first?
*(Requires: CoreRule "March Move", Difficult Terrain movement penalty, interaction between the two.)*

**Q6 (M,R)** A Chaos Knight unit with the Mark of Nurgle has a special rule that reduces enemy
models' Initiative. They are charged by a High Elf unit with Always Strikes First (ASF). In
what Initiative order does combat resolve? Does ASF override the Initiative reduction?
*(Requires: SpecialRule "ASF" (High Elves), SpecialRule "Mark of Nurgle Initiative penalty",
CoreRule Initiative strike order, interaction/priority rules.)*

**Q7 (M,R)** A unit of Dwarf Thunderers (crossbow infantry) is on a Hill. They fire at an
enemy unit behind a Low Linear Obstacle on the opposite side of the hill. Does the hill's
elevation allow them to see over the obstacle? Do the enemies still get a cover save?
*(Requires: Terrain "hills" LOS extension, Terrain "low linear obstacle" cover rules, shooting
CoreRules.)*

---

### Section B — Combat Resolution and Rank Bonus

**Q8 (C,R)** A 20-model unit of Skaven Clanrats (Infantry, 5-per-rank minimum) is arranged
5 wide and 4 deep. They are fighting a 10-model unit of Empire Halberdiers (5 wide, 2 deep).
The Clanrats win combat by 1 wound. What is the Clanrats' Rank Bonus? How many ranks count?
*(Requires: TroopType "Infantry" → min_models_for_rank_bonus = 5, max_rank_bonus = 3, formation
calculation.)*

**Q9 (C,R,M)** A unit of Chaos Warriors (Heavy Infantry) 6 wide and 3 deep is in combat.
They charged this turn and have Great Weapons. Their S is 5. The enemy has T4 and AV 4+.
In what order do they strike? What to-wound roll is needed? What is the enemy's effective
armour save after Great Weapon AP?
*(Requires: Weapon "Great Weapon" → S+2, AP −2, Strikes Last, TroopType "Heavy Infantry" rank
bonus, Wound table S7 vs T4, AV 4+ modified by AP −2.)*

**Q10 (M,R,C)** A Bretonnian Knight of the Realm unit (Lance, Barded Warhorse, Heavy Armour,
Shield) is charged in the flank by an Orc Boar Boyz unit (Spears, Light Armour). The Orc
player wins the combat by 2 wounds (after calculating rank bonus, outnumber, etc.). What
Break Test does the Knight unit take, and what modifiers apply?
*(Requires: flank charge modifier to combat resolution, rank bonus for both sides, outnumber
check, Ld of Bretonnian Knights, Break Test rules.)*

**Q11 (R,M)** A Monster (Manticore, W5, T5) is in base contact with a unit of Empire
Swordsmen. The Swordsmen inflict 3 unsaved wounds on the Manticore. Does the Manticore fight
back this round despite taking wounds? Does the Manticore's stat profile degrade as it takes
wounds?
*(Requires: Monster troop type combat rules, multi-wound resolution, whether TOW uses
degrading profiles like later editions or not.)*

**Q12 (M,R,C)** A unit of Black Orcs (Heavy Infantry, Fear-causing) is fighting a unit of
Goblin Wolf Riders (Cavalry). The Black Orcs have Unit Strength 20; Wolf Riders have Unit
Strength 12. The Black Orcs cause Fear. Do the Wolf Riders need to take a Fear Test? What
happens if they fail?
*(Requires: Fear rule, outnumber check via Unit Strength, Fear test result on failure, TroopType
US per model for both.)*

**Q13 (C,R)** A Vampire Lord (Character, Ld 10) joins a unit of Skeleton Warriors (Undead,
Ld 4). The unit loses a combat round by 3 wounds. What happens? Do they take a Break Test?
How many wounds do they suffer from Crumble?
*(Requires: Undead special rule (Unstable/Crumble), no Break Test for Undead, auto-wound equal
to combat loss, Vampire's Ld irrelevance to Crumble, Undead Hierarchy and Hierophant rules.)*

**Q14 (R,M)** A unit of Grave Guard with great weapons is fighting in combat. They have the
"Killing Blow" special rule. One of their to-wound rolls is a 6. The target is a Chaos Warrior
character with a Ward Save of 4+. Can the Ward Save negate the Killing Blow? What about a
Regeneration save?
*(Requires: SpecialRule "Killing Blow" (no saves allowed), interaction with Ward Save and
Regeneration, exceptions for certain character types.)*

---

### Section C — Magic Phase and Spells

**Q15 (R,C)** A Level 4 Vampire Lord attempts to cast Invocation of Nehek (Necromancy Lore
Signature Spell) using 4 Power Dice. He rolls 5, 4, 3, 1 = total 13. The opponent uses 2
Dispel Dice and rolls 6, 5 = 11. Does the spell go off? What happens to the opponent's
remaining Dispel Dice?
*(Requires: Casting vs dispel total comparison, spell resolution, spell type "Enchantment" vs
ability to be dispelled, DD expenditure rules.)*

**Q16 (M,R)** A Goblin Shaman (Level 2) knows spells from Little Waaagh! Lore. Can he use
Power Dice generated by the Orc Waaagh! Lore Shaman in the same army? Is the Winds of Magic
Power Dice pool shared among all friendly wizards?
*(Requires: CoreRule "Magic Phase" PD pool sharing, lore restrictions, army wizard stacking rules.)*

**Q17 (R,M)** A High Elf Archmage is targeted by a Hex spell while standing alone (not in
a unit). He has a Talisman of Protection (Ward Save 4+) and Magic Resistance (2). The spell
has a casting value of 8 and was cast on a total of 12 with 3 PD. The Archmage's player uses
Magic Resistance. How many Dispel Dice do they use? Can the talisman Ward Save protect against
a Hex?
*(Requires: Magic Resistance rule (+X DD when targeted), Hex spell mechanics, Ward Save timing
vs spell types.)*

**Q18 (M,R,C)** A Tomb Kings army has a Liche Priest Hierophant who is the army's "linchpin."
During the Magic Phase, the Hierophant is dispelled mid-incantation. The army has Undead
Crumble rules. What happens to the Undead units at end of phase if the Hierophant is destroyed?
*(Requires: Tomb Kings specific rule — Hierophant death triggers Crumble test for all Undead,
TK Incantations as magic system, interaction with Undead Instability.)*

**Q19 (R,M)** A Skaven player has a Grey Seer (Level 4 Wizard) with the Dreaded 13th Spell
(Warp Lightning Lore or Grey Seer lore). The spell is successfully cast. The target is a unit
of Chaos Warriors (T4, AV 2+, Immune to Psychology). How does the Dreaded 13th interact with
Chaos Warriors who might have Daemon-given Ward Saves?
*(Requires: Dreaded 13th spell mechanics, Chaos Warriors stats and saves, spell type, whether
it bypasses armour/ward saves.)*

**Q20 (R,C)** A Wizard has a Remains in Play spell active on a friendly unit. In the next
Magic Phase, the opponent successfully dispels it. The spell was granting the unit +1T and
regeneration. Does the unit immediately lose both effects? Does the dispel affect the current
combat round in progress?
*(Requires: "Remains in Play" spell rules, dispel timing, effect removal.)*

**Q21 (M,R)** A Dwarf Runesmith has the Rune of Spellbreaking. When the opponent casts a spell,
the Runesmith declares use of the Rune. What is the mechanical effect? How does it differ from
a standard Dispel Die roll? Can it be used multiple times per phase?
*(Requires: Dwarfs' Rune system (not standard magic), Rune of Spellbreaking specific text,
no-wizard magic rules for Dwarfs.)*

---

### Section D — Army List Building

**Q22 (A,C)** A player is building a 2,000pt Vampire Counts Grand Army. They want to include
a Vampire Lord (350 pts), two units of Blood Knights (39 pts/model × 5 = 195 pts each),
and fill the rest with Skeleton Warriors and Zombies. How many total points are available for
Characters, Core, Special, and Rare categories? Are two units of Blood Knights legal?
*(Requires: Army composition_percentages, Blood Knights as Rare unit, army category limits,
calculation of remaining points per category.)*

**Q23 (A,M)** An Empire player wants to take a Steam Tank. Is it a Rare unit? What are the
additional restrictions on taking one? Can the Steam Tank be included in an Allied Contingent
for another army?
*(Requires: Steam Tank army_category, per-unit restriction (0–1), ally rules — allied units
follow their own army's restrictions.)*

**Q24 (A,R)** A Bretonnia player wants to include Tomb Kings cavalry as Desperate Allies.
What is the alliance type between Bretonnia and Tomb Kings? What restrictions apply to
Desperate Allies in the army? What percentage cap do they count against?
*(Requires: ALLIED_WITH edge Bretonnia → Tomb Kings, alliance_type "desperate", Desperate
Allies rules, 25% Allies cap.)*

**Q25 (A,C,M)** A player building an Orcs & Goblins army wants maximum trolls. Trolls are
a Special unit with Stupidity. Can they have more than one unit of trolls? What is the max
% for Special, and if the army is 2,000 pts, how many points can be spent on trolls?
*(Requires: Trolls army_category = Special, composition_percentages Special = max 50%, per-unit
restriction check, Stupidity special rule text.)*

**Q26 (A,R,C)** A Warriors of Chaos player wants a Chaos Lord on a Chaos Dragon. They also
want to give him the Chaos Runeshield (Magic Armour) and the Collar of Khorne (Talisman).
Is this legal? What is the combined AV? What Ward Save does the Collar provide?
*(Requires: Character magic item budget, single magic armour restriction, AV of Chaos Dragon
(mount) + Chaos Runeshield, Collar of Khorne Ward Save text.)*

**Q27 (A,R)** A High Elf player wants to include Sea Guard in their army. Sea Guard can be
taken as both Core and Special depending on configuration. What is the difference, and how
does this affect army composition percentages?
*(Requires: Unit army_category as List<String> (multiple categories), category-specific upgrade
conditions, composition calculation.)*

**Q28 (A,M,C)** A Vampire Counts player wants a unit of Blood Knights with a Magic Standard
(50 pt budget). They choose the Banner of the Dead Legion. Does this banner go over budget?
What is the standard bearer upgrade cost on top of the banner cost?
*(Requires: Blood Knights HAS_UPGRADE command_standard, magic_standard_budget, MagicItem "Banner
of the Dead Legion" points_cost, upgrade cost calculation.)*

---

### Section E — Special Rule Interactions

**Q29 (R,M)** A Chaos Sorcerer casts a spell that grants his unit Flaming Attacks. The target
unit has the Flammable special rule. Does the Flaming Attacks buff stack with additional magical
attacks in the same unit, or is it applied once? What is the practical effect on a Flammable
unit with Regeneration?
*(Requires: SpecialRule "Flaming Attacks", SpecialRule "Flammable" (double wounds), interaction
with "Regeneration" (Flaming negates Regen), stacking rules.)*

**Q30 (M,R)** A High Elf Phoenix Guard unit has Ward Save 4+. They are charged by a unit with
Killing Blow. One Phoenix Guard suffers a Killing Blow. Can the Phoenix Guard use their Ward
Save against it?
*(Requires: SpecialRule "Killing Blow" text — no armour OR ward saves; contrast with some
unit-specific exceptions that override this.)*

**Q31 (R,M)** A Goblin Shaman has the Itty Bitty But Effective spell, granting +1 Strength.
A Goblin unit also has spears. Does the +1S from the spell stack with the Spear weapon profile,
which already has no S modifier? What is the effective Strength for the attack?
*(Requires: Spell buff stacking with weapon profile, Spear no S modifier, total S calculation.)*

**Q32 (R,M)** A unit of Chaos Warriors with Mark of Khorne has Frenzy. They are positioned
30" from the nearest enemy unit. At the start of movement, must they attempt to charge? Can
Frenzy force a failed charge attempt that would leave them stranded in the open?
*(Requires: SpecialRule "Frenzy" charge compulsion, range of charge (2× M), what happens on
failed charge when Frenzied — unit still moves forward max distance.)*

**Q33 (M,R)** A Vampire character with the "Dread Knight" upgrade has the Iron Resolve vampiric
power. They join a unit of Grave Guard. The Vampire has Ld 10 and Stubborn. If the Grave Guard
unit loses combat, what Leadership value do they use for the Break Test, and does Stubborn apply?
*(Requires: Character joining unit Leadership sharing, Stubborn rule (use unmodified Ld), Undead
vs. Stubborn interaction (Undead don't test — they Crumble), Vampire Counts Undead Hierarchy.)*

**Q34 (M,R,C)** A Steam Tank fires its Steam Gun at a unit of Skaven Plague Monks (T3, no
armour, Flammable). The Steam Gun fires 2D6 hits at S5. The player rolls 8 hits. All hit and
wound. How many wounds does the unit suffer? Does Flammable double each wound or the total?
*(Requires: Steam Gun firing profile, S5 vs T3 wound roll, no armour = no save, Flammable rule
doubling of wounds, calculation.)*

**Q35 (R,M)** A Tomb Scorpion (Tomb Kings) has the "Killing Blow" special rule and the
"Entombed Beneath the Sands" rule (ambush from underground). It surfaces inside a unit.
Does it get to fight immediately in the movement phase, or does it wait until the Close
Combat phase? Does it get to use Impact Hits from emerging?
*(Requires: "Entombed Beneath the Sands" rule text, arrival timing, Impact Hits applicability
only on a charge, Killing Blow in regular combat.)*

**Q36 (R,M)** An Ogre unit with the "Maw" army rule has Gut Magic available. One Ogre
Butcher (Wizard) casts a spell that grants the Ogre unit Regeneration 5+. The Ogre unit is
then hit by attacks with Flaming Attacks. Does Regeneration save work? What if some attacks
are Flaming and some are not — can the unit regenerate wounds from non-flaming attacks in
the same phase?
*(Requires: SpecialRule "Regeneration" + "Flaming Attacks" negation interaction, per-wound
vs. per-phase application.)*

---

### Section F — Complex Multi-Hop Scenarios

**Q37 (M,R,C)** A player is designing a list and wants to know the most armour-saves-efficient
Chaos Knight configuration possible. The knights have Full Plate Armour, shields, and barding
on their mounts. What is their final AV? If they also take the Mark of Tzeentch (Ward Save 5+),
what is their combined survivability against S4 AP −1 attacks?
*(Requires: AV calculation recipe — Full Plate + Shield + Barding, Cavalry cap 2+, Ward Save
from Mark of Tzeentch, AP modifier reducing effective AV, combined probability of negating a
wound.)*

**Q38 (M,R,C)** A Dwarf Cannon fires at a unit of 20 Orcs arranged 5 wide, 4 deep. The
cannonball bounces through the front rank (hitting 5 models) and continues bouncing 8" through
the unit. The cannon fires at S10 AP−3. The Orcs have Light Armour (6+ save). How many to-wound
rolls does the player make? What is the effective armour save of each model hit?
*(Requires: Cannon bounce mechanics (hits each rank in line), to-wound S10 vs T4 Orcs, AV 6+
modified by AP −3 = no save, War Machine weapon profile.)*

**Q39 (M,R)** A High Elf Archmage riding a Star Dragon (Monstrous Cavalry, Fear, Fly) charges
into a unit of Empire Swordsmen supported by a Detachment. The Swordsmen pass their Fear Test.
The Dragon has the Fire Breath special rule. Does the Dragon use the Breath Weapon on the
charge? If so, when exactly — before combat, during, or instead of close combat attacks?
*(Requires: Breath Weapon timing on the charge, Star Dragon profile (Monstrous Cavalry), Fear
Test mechanics, Empire Detachment counter-charge rules.)*

**Q40 (M,R,A)** A Vampire Counts player wants to use "Invocation of Nehek" to bring back
models to a unit of Skeleton Warriors that has been reduced below half strength. The spell
adds D6+1 models. Is there a cap on how many models can be returned? Can the unit exceed its
starting model count? Can the spell bring back a destroyed unit from scratch?
*(Requires: Invocation of Nehek spell text, Undead resurrection rules, unit rebuild vs. reinforcement
distinction.)*

**Q41 (M,R,C)** A unit of Bretonnian Grail Knights (Immune to Psychology, Ward Save 5+ from
the Blessing of the Lady) charges into a unit of Vampire Count Blood Knights (Fear-causing,
Undead). Do the Grail Knights need to take a Fear Test? The Blood Knights have US 15; the
Grail Knights have US 12. What combat resolution modifiers apply for both sides?
*(Requires: Grail Knights "Immune to Psychology" → no Fear test, US comparison for outnumber,
both sides' rank bonuses, charge bonus, standard bearer checks.)*

**Q42 (R,M,C)** An Orc Warboss (Ld 8) is the General of an Orc army. He is killed in close
combat mid-game. The remaining army must now check for Panic. Which units are affected, and
what Ld value do they use? Are any units exempt from the Panic Test (e.g. Black Orcs)?
*(Requires: General death Panic Test mechanics, radius or army-wide effect, Black Orcs' Immune
to Psychology or special morale rule, fallback Leadership after General dies.)*

**Q43 (M,R)** A Skaven Warlock Engineer has a Warp Lightning Cannon. During the Shooting
Phase, the cannon misfires. The player rolls on the War Machine Misfire table and gets a result
that destroys the machine. Does the crew remain on the table? Do they count as a unit for army
composition purposes? Can they still contribute to the battle in any way?
*(Requires: War Machine Misfire table result, crew rules after machine destruction, crew as
separate unit vs. machine unit interaction.)*

**Q44 (M,R,A,C)** A Grand Cathay player wants to maximize the Harmony mechanic (Dragon and
Phoenix synergy, yin/yang balance). Their General is a Monkey King (Special Character). They
have two units of Jade Warriors (Core) and one unit of Sky-Junk (Rare). What is the Harmony
activation requirement, and what army composition constraints must they keep in mind?
*(Requires: Grand Cathay Harmony mechanic rules, composition percentages, Special Character
restrictions.)*

**Q45 (M,R)** A unit of Wood Elf Waywatchers uses the "Scouts" rule and deploys in a woods
during set-up. They also have "Skirmishers" and "Move Through Cover." During the game, they
shoot at an enemy approaching the woods. The enemy unit has a character with a Magic Standard
that grants Magic Resistance (2). Does Magic Resistance help against the Waywatchers' mundane
bow shots?
*(Requires: Magic Resistance applicability (only vs spells), Waywatcher special rules and
shooting bonuses, "Move Through Cover" cover interaction.)*

**Q46 (C,R,M)** A player wants to know if their Chaos Warrior Champion can issue and accept
challenges. The Chaos Warriors unit is engaged in combat with a unit of Dwarfs including a
Thane character. The Chaos Champion issues a challenge. The Thane accepts. What modifiers
apply? If the Chaos Champion has a Chaos Weapon that deals 2 extra wounds to characters, does
this trigger on the Champion's attacks only?
*(Requires: Challenge rules (CoreRule), Champion vs. character combat, magic weapon "extra
wounds to characters" rule, unit strength and rank bonus during challenge.)*

**Q47 (M,R)** During deployment, a Tomb Kings player declares that their Tomb Scorpion will
use "Entombed Beneath the Sands." Later, the same player wants to use a Khalida's Venom
Archers unit (which has special deployment rules too). Can two units with different
special deployment rules be used simultaneously? What is the order of special deployment
resolution?
*(Requires: Multiple special deployment rules, simultaneous deployment resolution order,
CoreRule deployment phase.)*

---

### Section G — Edge Cases and Rule Interactions

**Q48 (R,M)** A Vampire character with Ld 10 is in a unit of Zombies (Ld 4). The Vampire
has "Inspiring Presence" range. A nearby unit of Skeletons (Ld 3) loses combat. Can the
Skeletons use the Vampire's Ld 10? Does it matter that the Vampire is in the Zombie unit, not
the Skeleton unit?
*(Requires: General's "Inspiring Presence" 12" radius rule, Ld use in tests when character
is in a different unit, Undead Crumble vs. Break Test.)*

**Q49 (R,M,C)** A Dark Elf Hydra has "Regeneration 4+". It is hit by 6 wounds from a unit
with Flaming Attacks and 4 wounds from a unit without Flaming Attacks. The non-flaming attacks
happen first in initiative order. Can the Hydra regenerate the non-flaming wounds even though
flaming attacks were also directed at it this phase?
*(Requires: Regeneration per-wound vs. per-phase resolution, Flaming Attacks negation timing,
wound allocation order.)*

**Q50 (M,R,C)** A player fields an Ogre Kingdoms army with a Tyrant (General, Ld 9), an
Irongut unit (Monstrous Infantry), and a Scraplauncher (Gnoblar-crewed chariot/monster).
The opponent casts a Terror-causing spell effect. The Ironguts are Immune to Psychology. The
Scraplauncher is not. What tests does each unit take, and what Ld values do they use?
*(Requires: Terror test rules, Immune to Psychology exemption, Inspiring Presence distance
check, General's Ld 9 vs. unit's own Ld for Scraplauncher.)*

**Q51 (R,M)** A unit of Empire Flagellants has the special rule "Unbreakable" and "No
Retreat." They are flanked and suffer a combat loss of 4. They cannot flee. Do they suffer
any penalty? If a Warrior Priest's prayer grants them "+1 Wound" per model, does this interact
with their Unbreakable status or the "No Retreat" wound resolution?
*(Requires: Unbreakable rule (never flee, never Break Test), No Retreat interaction, prayer
buff, Flagellants' unique rules.)*

**Q52 (M,R,C)** Two armies are being compared for their ability to crack through Chaos
Warrior heavy armour (AV 2+ from Full Plate + Shield + Barding). Army A has a Hellblaster
Volley Gun (S4, AP0, multiple shots). Army B has a Dwarf Organ Gun (S5, AP −1). Which has
better expected wounds per turn against this target? What if the Chaos Warriors have a Ward
Save 5+ from Mark of Tzeentch?
*(Requires: both war machine profiles, AV 2+ save, AP modification, Ward Save stacking, expected
probability calculation.)*

**Q53 (M,R)** A unit has the "Stubborn" special rule and is also within 12" of the General
(Ld 9). They lose a combat by 4 wounds. What Ld do they use for the Break Test, and what
modifiers apply? If they are fighting against an enemy that causes Fear and they failed their
earlier Fear Test (suffering "Strikes Last"), does the Fear Test failure carry any modifier
into the Break Test?
*(Requires: Stubborn rule (unmodified Ld), General's Ld proximity, Fear Test failure effect
(Strikes Last only, not a Ld modifier to Break Test), Break Test modifier from combat loss.)*

**Q54 (M,R,A)** A player wants to know if a Chaos Spawn counts toward any army composition
category. It is a Common Special unit in some lists but Rare in others. It has Random Movement
and Random Attacks. What army category does it fall under in the Warriors of Chaos book? Does
it count toward the 50% Special cap or the 25% Rare cap?
*(Requires: Chaos Spawn army_category in Warriors of Chaos, composition percentage, special
vs. rare classification.)*

**Q55 (M,R)** A High Elf Dragon Mage (Wizard on Dragon, Fire magic affinity) has access to
the Lore of Fire. The Dragon itself has a Breath Weapon (Fire). If the Dragon Mage also casts
a Fireball spell, does the Dragon's Breath Weapon count as the same "fire attack" for
Flammable doubling purposes? Can both the spell AND the Breath Weapon be used in the same turn?
*(Requires: Fire Breath timing (charge or shooting phase), Fireball spell type (Magic Missile),
Flammable rule (any flaming attack doubles wounds), Lore of Fire affinity bonus.)*

**Q56 (R,M,C)** A Vampire Counts player fields a Black Coach. The Black Coach has a profile
that improves as it feeds on magic ("Evocation of Death"). It starts with certain stats and
gains abilities at milestones. At the start of the game it has T5. After absorbing 3 Power Dice,
it gains +1W. Does this make it more durable against S5 attacks, or does T remain the same?
*(Requires: Black Coach profile, Evocation of Death special rule, stat progression, T5 vs S5
wound roll.)*

**Q57 (M,R)** An Orc Big Boss with the "Waaagh!" ability has Orcs nearby. Can he trigger the
Waaagh! multiple times in a game? What is the condition for triggering it? Do Goblin units
in the army benefit from the Waaagh! or only Orc units?
*(Requires: Waaagh! rule text, trigger conditions, frequency, affected unit types (Orcs vs.
Goblins).)*

**Q58 (M,R,C)** A Skaven Clan Moulder player has Rat Ogres and a Packmaster. The Packmaster
has the "Whips" upgrade that prevents Rat Ogres from needing Packmasters nearby. The unit is
charged in the flank. Rat Ogres have Random Attacks (2D6). How many attacks does the unit
generate? Does the Packmaster count as part of the unit for rank bonus purposes?
*(Requires: Rat Ogre profile → Random Attacks rule, Packmaster rules, flank charge combat
resolution, unit composition with special model (Packmaster).)*

---

*End of domain knowledge document.*
*Total questions: 58*
*Entity types covered: Army, Unit, TroopType, SpecialRule, CoreRule, Weapon, Spell, Lore,*
*MagicItem, Terrain, FAQ/Errata, Upgrade, Profile, ALLIED_WITH edges, TERRAIN_INTERACTION edges.*
