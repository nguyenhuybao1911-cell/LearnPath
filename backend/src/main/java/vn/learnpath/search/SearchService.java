package vn.learnpath.search;

import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.*;

@Service
public class SearchService {
    public record Concept(String id, String name) {}
    public record Edge(String prerequisite, String concept) {}
    public record Mastery(int correct, int total) {
        public double value() { return total == 0 ? 0.5 : (double) correct / total; }
    }
    public record Weights(double p, double n, double d, double r) {
        public Weights {
            double sum = p + n + d + r;
            if (!Double.isFinite(sum) || p < 0 || n < 0 || d < 0 || r < 0 || Math.abs(sum - 1.0) > 1e-9)
                throw new IllegalArgumentException("Heuristic weights must be nonnegative and sum to 1");
        }
    }
    public record Settings(double tau, int minInteractions, Weights weights, int maxStates,
                           Duration timeLimit, Set<String> allowedConcepts) {
        public Settings {
            if (tau < 0 || tau > 1 || minInteractions < 0 || maxStates < 1 || timeLimit.isNegative() || timeLimit.isZero())
                throw new IllegalArgumentException("Invalid search settings");
            allowedConcepts = allowedConcepts == null ? Set.of() : Set.copyOf(allowedConcepts);
        }
    }
    public record Scores(double p, double n, double d, double r, double h, Double mastery, String explanation) {}
    public record Step(String conceptId, String conceptName, Scores scores) {}
    public record Result(String learnerId, String targetId, String status, List<Step> steps,
                         int expanded, int peakOpen, String message) {}
    private record State(List<String> path, Set<String> completed, double score, String last) {}

    public Result recommend(String learnerId, String targetId, Map<String, Concept> concepts, List<Edge> edges,
                            Map<String, Mastery> mastery, Map<String, Double> difficulty, Settings settings) {
        if (!concepts.containsKey(targetId)) throw new IllegalArgumentException("Unknown target concept: " + targetId);
        Map<String, Set<String>> prerequisites = validateGraph(concepts, edges);
        Map<String, Integer> distance = distances(targetId, prerequisites);
        Set<String> allowed = settings.allowedConcepts().isEmpty() ? concepts.keySet() : settings.allowedConcepts();
        if (!allowed.contains(targetId)) return result(learnerId, targetId, "no_path", "Mục tiêu nằm ngoài phạm vi đã chọn.", 0, 0);

        Set<String> initial = new HashSet<>();
        mastery.forEach((id, value) -> {
            if (concepts.containsKey(id) && value.total() >= settings.minInteractions() && value.value() >= settings.tau()) initial.add(id);
        });
        if (initial.contains(targetId)) return result(learnerId, targetId, "target_already_mastered",
                "Mục tiêu đã đạt ngưỡng thành thạo từ dữ liệu quan sát.", 0, 0);
        if (!distance.containsKey(targetId)) return result(learnerId, targetId, "no_path", "Không có đường prerequisite tới mục tiêu.", 0, 0);

        double ability = mastery.values().stream().filter(m -> m.total() > 0).mapToDouble(Mastery::value).average().orElse(.5);
        Comparator<State> order = Comparator.comparingDouble(State::score).reversed()
                .thenComparing(State::last).thenComparing(s -> String.join("\u0000", s.path()));
        PriorityQueue<State> open = new PriorityQueue<>(order);
        Set<List<String>> seen = new HashSet<>();
        seen.add(List.of());
        addChildren(open, seen, List.of(), initial, allowed, prerequisites, distance, mastery, difficulty, ability, settings.weights());
        int peakOpen = open.size(), expanded = 0;
        long deadline = System.nanoTime() + settings.timeLimit().toNanos();

        while (!open.isEmpty() && expanded < settings.maxStates() && System.nanoTime() < deadline) {
            State state = open.remove();
            expanded++;
            if (state.completed().contains(targetId)) {
                List<Step> steps = new ArrayList<>();
                Set<String> completed = new HashSet<>(initial);
                for (String id : state.path()) {
                    Scores scores = score(id, completed, prerequisites, distance, mastery, difficulty, ability, settings.weights());
                    steps.add(new Step(id, concepts.get(id).name(), scores));
                    completed.add(id);
                }
                return new Result(learnerId, targetId, "reached", List.copyOf(steps), expanded, peakOpen,
                        "Đã tìm thấy lộ trình hợp lệ bằng Greedy Best-First; không bảo đảm tối ưu toàn cục.");
            }
            addChildren(open, seen, state.path(), state.completed(), allowed, prerequisites, distance, mastery, difficulty, ability, settings.weights());
            peakOpen = Math.max(peakOpen, open.size());
        }
        boolean exhausted = !open.isEmpty();
        return result(learnerId, targetId, exhausted ? "budget_exhausted" : "no_path",
                exhausted ? "Hết ngân sách trạng thái hoặc thời gian tìm kiếm." : "Không tìm thấy lộ trình thỏa prerequisite.", expanded, peakOpen);
    }

    private void addChildren(PriorityQueue<State> open, Set<List<String>> seen, List<String> path, Set<String> completed,
                             Set<String> allowed, Map<String, Set<String>> prerequisites, Map<String, Integer> distance,
                             Map<String, Mastery> mastery, Map<String, Double> difficulty, double ability, Weights weights) {
        distance.keySet().stream().filter(allowed::contains).filter(id -> !completed.contains(id))
                .filter(id -> completed.containsAll(prerequisites.getOrDefault(id, Set.of())))
                .sorted().forEach(id -> {
                    List<String> nextPath = new ArrayList<>(path);
                    nextPath.add(id);
                    nextPath = List.copyOf(nextPath);
                    if (!seen.add(nextPath)) return;
                    Scores scores = score(id, completed, prerequisites, distance, mastery, difficulty, ability, weights);
                    Set<String> nextCompleted = new HashSet<>(completed);
                    nextCompleted.add(id);
                    open.add(new State(nextPath, Set.copyOf(nextCompleted), scores.h(), id));
                });
    }

    private Scores score(String id, Set<String> completed, Map<String, Set<String>> prerequisites,
                         Map<String, Integer> distance, Map<String, Mastery> mastery,
                         Map<String, Double> difficulty, double ability, Weights weights) {
        Set<String> parents = prerequisites.getOrDefault(id, Set.of());
        double p = parents.isEmpty() ? 1.0 : (double) parents.stream().filter(completed::contains).count() / parents.size();
        Mastery row = mastery.get(id);
        Double m = row == null || row.total() == 0 ? null : row.value();
        double n = 1.0 - (m == null ? .5 : m);
        double dEstimate = Math.max(0, Math.min(1, difficulty.getOrDefault(id, .5)));
        double d = 1.0 - Math.abs(dEstimate - ability);
        double r = 1.0 / (1 + distance.get(id));
        double h = weights.p() * p + weights.n() * n + weights.d() * d + weights.r() * r;
        String observed = m == null ? "chưa có dữ liệu mastery" : String.format(Locale.ROOT, "mastery quan sát %.2f", m);
        String explanation = String.format(Locale.ROOT,
                "Prerequisite sẵn sàng (%.0f%%); %s; độ phù hợp độ khó %.2f; cách mục tiêu %d cạnh.", p * 100, observed, d, distance.get(id));
        return new Scores(p, n, d, r, h, m, explanation);
    }

    private Map<String, Set<String>> validateGraph(Map<String, Concept> concepts, List<Edge> edges) {
        Map<String, Set<String>> prerequisites = new HashMap<>();
        Map<String, Set<String>> children = new HashMap<>();
        Map<String, Integer> indegree = new HashMap<>();
        concepts.keySet().forEach(id -> indegree.put(id, 0));
        for (Edge edge : new HashSet<>(edges)) {
            if (!concepts.containsKey(edge.prerequisite()) || !concepts.containsKey(edge.concept()))
                throw new IllegalArgumentException("Unknown concept in prerequisite edge: " + edge);
            if (edge.prerequisite().equals(edge.concept())) throw new IllegalArgumentException("Self-loop: " + edge.prerequisite());
            prerequisites.computeIfAbsent(edge.concept(), key -> new HashSet<>()).add(edge.prerequisite());
            if (children.computeIfAbsent(edge.prerequisite(), key -> new HashSet<>()).add(edge.concept()))
                indegree.compute(edge.concept(), (key, value) -> value + 1);
        }
        PriorityQueue<String> roots = new PriorityQueue<>();
        indegree.forEach((id, degree) -> { if (degree == 0) roots.add(id); });
        int count = 0;
        while (!roots.isEmpty()) {
            String parent = roots.remove();
            count++;
            for (String child : children.getOrDefault(parent, Set.of())) {
                int value = indegree.compute(child, (id, degree) -> degree - 1);
                if (value == 0) roots.add(child);
            }
        }
        if (count != concepts.size()) throw new IllegalArgumentException("Cycle in prerequisite graph");
        return prerequisites;
    }

    private Map<String, Integer> distances(String target, Map<String, Set<String>> prerequisites) {
        Map<String, Set<String>> reverse = new HashMap<>();
        prerequisites.forEach((child, parents) -> parents.forEach(parent -> reverse.computeIfAbsent(child, key -> new HashSet<>()).add(parent)));
        Map<String, Integer> distance = new HashMap<>();
        ArrayDeque<String> queue = new ArrayDeque<>();
        distance.put(target, 0);
        queue.add(target);
        while (!queue.isEmpty()) {
            String child = queue.remove();
            for (String parent : reverse.getOrDefault(child, Set.of())) {
                if (!distance.containsKey(parent)) {
                    distance.put(parent, distance.get(child) + 1);
                    queue.add(parent);
                }
            }
        }
        return distance;
    }

    private Result result(String learnerId, String targetId, String status, String message, int expanded, int peakOpen) {
        return new Result(learnerId, targetId, status, List.of(), expanded, peakOpen, message);
    }
}
