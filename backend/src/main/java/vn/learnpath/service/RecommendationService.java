package vn.learnpath.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.learnpath.repository.PathRepository;
import vn.learnpath.search.SearchService;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

@Service
public class RecommendationService {
    public record MasteryView(String conceptId, String conceptName, Integer correct, Integer total,
                              Double mastery, String status, Instant asOf) {}
    public record Request(String learnerId, String targetId, Instant asOf, Double tau, Integer minInteractions,
                          Double wP, Double wN, Double wD, Double wR, Integer maxStates, Long timeLimitMs) {}
    public record InteractionRequest(String learnerId, String problemId, String logId, Boolean correct,
                                     Double score, Integer attempts, Instant submittedAt) {}

    private final PathRepository repository;
    private final SearchService search;
    @Value("${app.mastery.tau:0.5}") private double defaultTau;
    @Value("${app.mastery.min-interactions:1}") private int defaultMinInteractions;
    @Value("${app.heuristic.w-p:0.0}") private double defaultWP;
    @Value("${app.heuristic.w-n:0.1}") private double defaultWN;
    @Value("${app.heuristic.w-d:0.4}") private double defaultWD;
    @Value("${app.heuristic.w-r:0.5}") private double defaultWR;
    @Value("${app.search.max-states:10000}") private int defaultMaxStates;
    @Value("${app.search.time-limit-ms:2000}") private long defaultTimeLimit;

    public RecommendationService(PathRepository repository, SearchService search) {
        this.repository = repository;
        this.search = search;
    }

    public List<MasteryView> state(String learnerId, Instant asOf) {
        var concepts = repository.concepts();
        var observed = repository.mastery(learnerId, asOf);
        return concepts.stream().map(c -> {
            var value = observed.get(c.id());
            return value == null
                    ? new MasteryView(c.id(), c.name(), null, null, null, "unknown", asOf)
                    : new MasteryView(c.id(), c.name(), value.correct(), value.total(), value.value(), "observed", asOf);
        }).toList();
    }

    @Transactional
    public SearchService.Result recommend(Request request) {
        if (request.learnerId() == null || request.targetId() == null) throw new IllegalArgumentException("learnerId and targetId are required");
        Instant asOf = request.asOf() == null ? Instant.now() : request.asOf();
        double tau = request.tau() == null ? defaultTau : request.tau();
        int min = request.minInteractions() == null ? defaultMinInteractions : request.minInteractions();
        var weights = new SearchService.Weights(value(request.wP(), defaultWP), value(request.wN(), defaultWN),
                value(request.wD(), defaultWD), value(request.wR(), defaultWR));
        var settings = new SearchService.Settings(tau, min, weights,
                request.maxStates() == null ? defaultMaxStates : request.maxStates(),
                Duration.ofMillis(request.timeLimitMs() == null ? defaultTimeLimit : request.timeLimitMs()), java.util.Set.of());
        var result = search.recommend(request.learnerId(), request.targetId(), repository.conceptMap(), repository.prerequisites(),
                repository.mastery(request.learnerId(), asOf), repository.trainDifficulty(), settings);
        repository.saveRecommendation(request.learnerId(), request.targetId(), result, Map.of(
                "asOf", asOf, "tau", tau, "minInteractions", min, "weights", weights,
                "maxStates", settings.maxStates(), "timeLimitMs", settings.timeLimit().toMillis()));
        return result;
    }

    @Transactional
    public boolean addInteraction(InteractionRequest request) {
        if (request.learnerId() == null || request.problemId() == null || request.logId() == null || request.correct() == null || request.submittedAt() == null)
            throw new IllegalArgumentException("learnerId, problemId, logId, correct and submittedAt are required");
        if (request.attempts() != null && request.attempts() < 0) throw new IllegalArgumentException("attempts must be nonnegative");
        return repository.addInteraction(request.learnerId(), request.problemId(), request.logId(), request.correct(),
                request.score(), request.attempts(), request.submittedAt());
    }

    private double value(Double provided, double fallback) { return provided == null ? fallback : provided; }
}
