import itertools
import math
import random
import re

debug = True
debug_probabilities = True

# Loaded dynamically.
global_components = []

RANKED_CANDIDATES_FILE = "ranked-candidates"
CANDIDATE_MATCH_COUNTS_FILE = "match-counts"
CANDIDATE_VICTORY_COUNTS_FILE = "victory-counts"

# Elo parameters.
SPREAD = 400
INITIAL_RATING = 1000
K = 40 # Quite high as results should be fairly stable

# How likely we are to pick an item rather than consider the following items
RANKING_BIAS = 0.15

# How often to re-rank existing candidates instead of trying a new one.
RERANK_RATE = 0.1

# How often to try to arbitrarily replacing one instead of mutate existing candidates.
REPLACEMENT_RATE = 0.15

# How many candidates to consider simultaneously.
POOL_SIZE = 20

# What fraction of candidates are immune to culling.
CULLING_IMMUNE_FRACTION = 0.7

# In pool selection, the power of the weight generated from rating.
RATING_POWER = 1.006

# How often to do a pool selection vs a tournament selection.
POOL_SELECTION_RATE = 0.3

# How much to weight the component vs the combo rating (which is weighted by count).
BASE_WEIGHT = 6

def components_filename(i):
  return f"components{i}"

def component_ratings_filename(i):
  return f"component-ratings{i}"

def component_match_counts_filename(i):
  return f"component-match_counts{i}"

def combo_ratings_filename(i):
  return f"combo-ratings{i}"

def combo_match_counts_filename(i):
  return f"combo-match_counts{i}"

def win_probability(elo1, elo2):
  return 1.0 / (1.0 + 10 ** ((elo2 - elo1) / SPREAD))

def new_elo(result, elo1, elo2):
  expected = win_probability(elo1, elo2)
  return elo1 + K * (result - expected)

def candidate_display_name(candidate):
  return candidate.replace("-", "")

class RatingSet:
  def __init__(self):
    self.ratings = {}

  def get(self, candidate):
    return self.ratings.get(candidate, INITIAL_RATING)

  def update_with_result(self, result, entrant1, entrant2):
    score1 = self.ratings.get(entrant1, INITIAL_RATING)
    score2 = self.ratings.get(entrant2, INITIAL_RATING)
    self.ratings[entrant1] = new_elo(result, score1, score2)
    self.ratings[entrant2] = new_elo(1.0 - result, score2, score1)

def save_rating_set(ratings, filename):
  with open(filename, 'w') as f:
    for candidate, rating in ratings.ratings.items():
      f.write(f'"{candidate}" {rating}\n')

RATING_RE = re.compile(r'"(?P<candidate>[a-z-]*)" (?P<rating>[0-9\.]+)')
def load_rating_set(filename):
  ratings = RatingSet()
  try:
    with open(filename, "r") as f:
      for line in f:
        line = line.strip()
        if (line == ''):
          continue
        candidate, ratingString = RATING_RE.fullmatch(line).group("candidate", "rating")
        rating = float(ratingString)
        ratings.ratings[candidate] = rating
  except FileNotFoundError:
    # Not an error, return empty set.
    if debug: print(f"ratings not found: {filename}")
    pass
  return ratings

class PerCandidateTally:
  def __init__(self):
    self.counts = {}

  def get(self, candidate):
    return self.counts.get(candidate, 0)

  def increment(self, candidate):
    self.counts.setdefault(candidate, 0)
    self.counts[candidate] += 1

def save_per_candidate_tally(tally, filename):
  with open(filename, 'w') as f:
    for candidate, count in tally.counts.items():
      f.write(f'"{candidate}" {count}\n')

TALLY_RE = re.compile(r'"(?P<candidate>[a-z-]*)" (?P<count>[0-9]+)')
def load_per_candidate_tally(filename):
  tally = PerCandidateTally()
  try:
    with open(filename, "r") as f:
      for line in f:
        line = line.strip()
        if (line == ''):
          continue
        candidate, countString = TALLY_RE.fullmatch(line).group("candidate", "count")
        count = int(countString)
        tally.counts[candidate] = count
  except FileNotFoundError:
    # Not an error, return empty set.
    if debug: print(f"counts not found: {filename}")
    pass
  return tally

def save_candidate_list(items, filename):
  with open(filename, 'w') as f:
    for item in items:
      f.write(f"{item}\n")

CANDIDATE_RE = re.compile(r"(?P<candidate>[a-z-]+)")
def load_candidate_list(filename):
  candidates = []
  try:
    with open(filename, "r") as f:
      for line in f:
        line = line.strip()
        if (line == ''):
          continue
        candidate = CANDIDATE_RE.fullmatch(line).group("candidate")
        candidates.append(candidate)
  except FileNotFoundError:
    # Not an error.
    return None
  return candidates

def weighted_selection(weighted_candidates):
    total = sum(w for _, w in weighted_candidates)
    r = random.uniform(0, total)
    cumulative_weight = 0
    for candidate, weight in weighted_candidates:
      cumulative_weight += weight
      if cumulative_weight >= r:
        return candidate
    raise "Shouldn't get here"

# Select an item from a ranked list, biasing towards the top items.
def ranked_selection(ranked_items):
  def ranked_weight(i):
    return (1 - RANKING_BIAS) ** i - (1 - RANKING_BIAS) ** (i + 1)

  weighted_candidates = (
      [(c, ranked_weight(i)) for i, c in enumerate(ranked_items)])
  return weighted_selection(weighted_candidates)

# Select an item from a ranked list, biasing towards the bottom items.
def culling_selection(ranked_items):
  n = len(ranked_items)
  immune_count = math.floor(CULLING_IMMUNE_FRACTION * n)
  def ranked_weight(i):
    if i < immune_count:
      return 0
    j = n - 1 - i
    return (1 - RANKING_BIAS) ** j - (1 - RANKING_BIAS) ** (j + 1)

  weighted_candidates = (
      [(c, ranked_weight(i)) for i, c in enumerate(ranked_items)])
  return weighted_selection(weighted_candidates)

# Weighted selection - odds shared as pool grows.
def pool_selection(ratings):
  # return sorted_candidates[-1][0]
  def weight(rating):
    return RATING_POWER ** rating

  weighted_candidates = (
    [(c, weight(r)) for c, r in ratings.items()])
  total_weight = sum(w for c, w in weighted_candidates)
  for c, w in weighted_candidates:
    if debug_probabilities: print(f"{c}: {w / total_weight}")
  result = weighted_selection(weighted_candidates)
  if debug_probabilities: print(f"winner: {result}")
  return result

# Weighted selection - top candidates dominate odds even for large pools.
def tournament_selection(ratings):
  # Sort the candidates by descending rating.
  sorted_candidates = sorted(list(ratings.items()), key=lambda x: x[1], reverse=True)
  for i in range(len(sorted_candidates) - 1):
    candidate, rating,  = sorted_candidates[i]
    XXX, next_rating = sorted_candidates[i + 1]
    # Simulate a match between this candidate and the next.
    # Flatten the probabilities somewhat; don't focus too much on past winners.
    win_rate = win_probability(rating, next_rating)
    if debug_probabilities: print(f"{candidate}({rating}) vs {XXX}({next_rating}), win_rate = {win_rate}")
    if random.uniform(0, 1) < win_rate:
      if debug_probabilities: print(f"winner: {candidate}")
      return candidate
  return sorted_candidates[-1]
  
# Select an item from a list of Elo-rated items, weighting according to win
# probability.
def rated_selection(ratings):
  # Mostly we do a tournament selection, which will reliably pick a top seed
  # regardless of pool size. However sometimes we do an alternative where the
  # chances are spread across all entrants, to get an occasional off-beat
  # suggestion.
  if random.uniform(0, 1) < POOL_SELECTION_RATE:
    if debug: print("pool selection")
    return pool_selection(ratings)
  else:
    if debug: print("tournament selection")
    return tournament_selection(ratings)


# Definition of a match to run.
class Match:
  def __init__(self, first, second):
    self.first = first
    self.second = second

def combos_for_candidate(candidate):
    return ['-'.join(x) for x in zip(candidate.split("-")[:-1], candidate.split("-")[1:])]

# Representation of an ongoing contest to determine the best name.
class Contest:
  def __init__(self):
    self.ranked_candidates = load_candidate_list(RANKED_CANDIDATES_FILE)

    # If no candidates exist, generate some initial ones.
    if self.ranked_candidates == None:
      if debug: print("candidates not found, generating new set.")
      self.ranked_candidates = [self.acceptable_new_generated_candidate() for x in range(POOL_SIZE)]

    self.candidate_match_counts = load_per_candidate_tally(CANDIDATE_MATCH_COUNTS_FILE)
    self.candidate_victory_counts = load_per_candidate_tally(CANDIDATE_VICTORY_COUNTS_FILE)
    self.component_ratings = (
      [load_rating_set(component_ratings_filename(i)) for i in range(len(global_components))])
    self.component_match_counts = (
      [load_per_candidate_tally(component_match_counts_filename(i)) for i in range(len(global_components))])
    self.combo_ratings = (
      [load_rating_set(combo_ratings_filename(i)) for i in range(len(global_components) - 1)])
    self.combo_match_counts = (
      [load_per_candidate_tally(combo_match_counts_filename(i)) for i in range(len(global_components) - 1)])

  def perform_match(self, candidate0, candidate1):
    print('1:', candidate_display_name(candidate0))
    print('2:', candidate_display_name(candidate1))
    selection = input("preference: ").strip()
    if selection == '1':
      result = 1
    elif selection == '2':
      result = 0
    else:
      raise "Invalid input: '" + selection + "'"

    # Update records.
    self.candidate_match_counts.increment(candidate0)
    self.candidate_match_counts.increment(candidate1)
    self.candidate_victory_counts.increment(candidate0 if result == 1 else candidate1)

    # Update component ratings.
    for i, (c0, c1) in enumerate(zip(candidate0.split("-"), candidate1.split("-"))):
      if c0 == c1:
        continue
      self.component_ratings[i].update_with_result(result, c0, c1)
      self.component_match_counts[i].increment(c0)
      self.component_match_counts[i].increment(c1)

    # Update combo ratings.
    combos0 = combos_for_candidate(candidate0)
    combos1 = combos_for_candidate(candidate1)
    for i, (c0, c1) in enumerate(zip(combos_for_candidate(candidate0), combos_for_candidate(candidate1))):
      if c0 == c1:
        continue
      self.combo_ratings[i].update_with_result(result, c0, c1)
      self.combo_match_counts[i].increment(c0)
      self.combo_match_counts[i].increment(c1)

    # Log match entry
    with open("match-log", "a+") as f:
      f.write(f"{candidate0} {candidate1} {result}\n")

    return result

  def candidate_is_acceptable(self, candidate):
    return self.candidate_match_counts.get(candidate) == 0

  def acceptable_new_generated_candidate(self):
    candidate = self.new_generated_candidate()
    while True:
      if self.candidate_is_acceptable(candidate):
        break
      candidate = self.mutated(candidate)
    return candidate

  def new_generated_candidate(self):
    components = []
    for i, options in enumerate(global_components):
      new_component = self.component_selection(components, i, options)
      components.append(new_component)
    return "-".join(components)

  # Mutate the candidate, possibly rejecting some undesirable options.
  def acceptably_mutated(self, candidate):
    while True:
      c = self.mutated(candidate)
      if self.candidate_is_acceptable(c):
        return c

  def mutated(self, candidate):
    def component_weight(i):
      return math.log(len(global_components[i]))
    components = candidate.split("-")
    weighted_component_indices = [(i, component_weight(i)) for i in range(len(components))]
    component_to_mutate_index = weighted_selection(weighted_component_indices)

    # Consider all the alternative components, apart from the existing one.
    replacement_options = (
        [c for c in global_components[component_to_mutate_index]
            if c != components[component_to_mutate_index]])

    replacement_component = self.component_selection(components, component_to_mutate_index, replacement_options)
    components[component_to_mutate_index] = replacement_component
    return "-".join(components)

  def component_selection(self, components, component_to_mutate_index, options):
    # Assign a weight to each option.
    # This weight is based on a blend of the ratings for the component and the
    # combos it is a part of.
    ratings = self.component_ratings[component_to_mutate_index]
    def weight_for_option(option):
      blend_total = ratings.get(option) * BASE_WEIGHT
      weight_total = BASE_WEIGHT

      # Blend in the rating for the combo of the previous component and this one.
      if component_to_mutate_index > 0:
        precombo_index = component_to_mutate_index - 1
        precombo = f"{components[component_to_mutate_index - 1]}-{option}"
        precombo_rating = self.combo_ratings[precombo_index].get(precombo)
        precombo_weight = self.combo_match_counts[precombo_index].get(precombo)
        blend_total += precombo_rating * precombo_weight
        weight_total += precombo_weight

      # Blend in the rating for the combo of this component and the next one.
      if component_to_mutate_index < len(components) - 1:
        combo_index = component_to_mutate_index
        combo = f"{option}-{components[component_to_mutate_index + 1]}"
        combo_rating = self.combo_ratings[combo_index].get(combo)
        combo_weight = self.combo_match_counts[combo_index].get(combo)
        blend_total += combo_rating * combo_weight
        weight_total += combo_weight

      blended_rating = blend_total / weight_total
      return blended_rating

    replacement_component = rated_selection(
        dict([(x, weight_for_option(x)) for x in options]))
      
    return replacement_component

  def maybe_perform_recent_entrant_match(self):
    # Look for an undefeated candidate who is not at the top, and return a
    # match between them and the candidate above them.
    for i in range(1, len(self.ranked_candidates)):
      candidate = self.ranked_candidates[i]
      undeated = self.candidate_victory_counts.get(candidate) == self.candidate_match_counts.get(candidate)
      if undeated:
        if debug: print(f"found recent, undefeated candidate: {candidate}")
        other_candidate = self.ranked_candidates[i - 1]
        result = self.perform_match(candidate, other_candidate)

        if result == 1:
          # The recent entrant beat the one above it, so swap them.
          if debug: print(f"moving new entrant up")
          self.swap_candidates(candidate, other_candidate)
        return True

    return False

  def perform_attempted_mutation_match(self):
    base_candidate = ranked_selection(self.ranked_candidates)
    mutated_candidate = self.acceptably_mutated(base_candidate)
    if debug: print(f"trying to mutate {base_candidate} into {mutated_candidate}")
    result = self.perform_match(mutated_candidate, base_candidate)
    if result == 1:
      if debug: print(f"mutation successful")
      self.replace_candidate(base_candidate, mutated_candidate)

  def replace_candidate_and_perform_first_match(self):
    # Pick a candidate to replace.
    old_candidate = culling_selection(self.ranked_candidates)

    # Mutate the candidate and move it to the bottom.
    new_candidate = self.acceptable_new_generated_candidate()

    if debug: print(f"replacing ({self.ranked_candidates.index(old_candidate)}) {old_candidate} with {new_candidate}")
    self.ranked_candidates.remove(old_candidate)
    bottom_candidate = self.ranked_candidates[len(self.ranked_candidates) - 1]
    self.ranked_candidates.append(new_candidate)

    # Match the new candidate against the second bottom one.
    result = self.perform_match(new_candidate, bottom_candidate)
    if result == 1:
      # The new candidate beat the previous bottom one, so swap them.
      if debug: print(f"swapping last two candidates: {new_candidate} & {bottom_candidate}")
      self.swap_candidates(new_candidate, bottom_candidate)

  def perform_rerank_match(self):
    # Pick a candidate to replace.
    indices = [i for i, x in enumerate(self.ranked_candidates)]
    candidate_indices = (
      [indices.pop(random.randrange(0, len(indices))),
       indices.pop(random.randrange(0, len(indices)))])
    candidates = sorted(
      ((self.ranked_candidates[i], i) for i in candidate_indices), key=lambda x: x[1])

    if debug: print(f"re-ranking {candidates[0][0]} and {candidates[1][0]}")
    result = self.perform_match(candidates[0][0], candidates[1][0])

    # If the lower-ranked candidate won, move it above the higher-ranked one.
    if result == 0:
      if debug: print(f"moving {candidates[1][0]} above {candidates[0][0]}")
      self.ranked_candidates.pop(candidates[1][1])
      self.ranked_candidates.insert(candidates[0][1], candidates[1][0])

  def select_and_perform_match(self):
    completed = self.maybe_perform_recent_entrant_match()
    if not completed:
      # Occasionally compare two existing candidates to see if rankings have
      # changed.
      if random.uniform(0, 1) < RERANK_RATE:
        self.perform_rerank_match()
      # Sometimes try to mutate an existing candidate, other times arbitrarily
      # replace one
      elif random.uniform(0, 1) < REPLACEMENT_RATE:
        self.replace_candidate_and_perform_first_match()
      else:
        self.perform_attempted_mutation_match()

  def update(self):
    self.select_and_perform_match()
    save_candidate_list(self.ranked_candidates, RANKED_CANDIDATES_FILE)
    save_per_candidate_tally(self.candidate_match_counts, CANDIDATE_MATCH_COUNTS_FILE)
    save_per_candidate_tally(self.candidate_victory_counts, CANDIDATE_VICTORY_COUNTS_FILE)
    for i, r in enumerate(self.component_ratings):
      save_rating_set(r, component_ratings_filename(i))
    for i, c in enumerate(self.component_match_counts):
      save_per_candidate_tally(c, component_match_counts_filename(i))
    for i, r in enumerate(self.combo_ratings):
      save_rating_set(r, combo_ratings_filename(i))
    for i, c in enumerate(self.combo_match_counts):
      save_per_candidate_tally(c, combo_match_counts_filename(i))

  def swap_candidates(self, candidate1, candidate2):
    l = self.ranked_candidates
    index1 = l.index(candidate1)
    index2 = l.index(candidate2)
    l[index2], l[index1] = l[index1], l[index2]

  def replace_candidate(self, old, new):
      i = self.ranked_candidates.index(old)
      self.ranked_candidates[i] = new

COMPONENT_RE = re.compile(r'"(?P<component>[a-z]*)"')
def load_component_list(filename):
  components = []
  try:
    with open(filename, "r") as f:
      for line in f:
        line = line.strip()
        if (line == ''):
          continue
        component = COMPONENT_RE.fullmatch(line).group("component")
        components.append(component)
  except FileNotFoundError:
    # Not an error.
    return None
    
  if len(components) == 0:
    raise f'No components in file "{filename}"'
  return components

def load_components():
  i = 0
  for i in itertools.count():
    component_options = load_component_list(components_filename(i))
    if component_options == None:
      break
    global_components.append(component_options)
  if len(global_components) == 0:
    raise 'No component files found'

def main():
  load_components()

  contest = Contest()
  contest.update()

if __name__ == '__main__':
  main()
