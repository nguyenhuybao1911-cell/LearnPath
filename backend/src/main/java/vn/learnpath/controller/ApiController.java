package vn.learnpath.controller;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import vn.learnpath.repository.PathRepository;
import vn.learnpath.search.SearchService;
import vn.learnpath.service.RecommendationService;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "${app.frontend-origin:http://localhost:5173}")
public class ApiController {
    private final PathRepository repository;
    private final RecommendationService recommendations;

    public ApiController(PathRepository repository, RecommendationService recommendations) {
        this.repository = repository;
        this.recommendations = recommendations;
    }

    @GetMapping("/health")
    public Map<String, Object> health() { return Map.of("status", "ok", "concepts", repository.conceptCount()); }

    @GetMapping("/learners")
    public List<String> learners() { return repository.learners(); }

    @GetMapping("/concepts")
    public List<SearchService.Concept> concepts() { return repository.concepts(); }

    @GetMapping("/learners/{learnerId}/state")
    public List<RecommendationService.MasteryView> state(@PathVariable String learnerId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant asOf) {
        return recommendations.state(learnerId, asOf == null ? Instant.now() : asOf);
    }

    @PostMapping("/recommendations")
    public SearchService.Result recommend(@RequestBody RecommendationService.Request request) {
        return recommendations.recommend(request);
    }

    @PostMapping("/interactions")
    public Map<String, Object> addInteraction(@RequestBody RecommendationService.InteractionRequest request) {
        boolean inserted = recommendations.addInteraction(request);
        return Map.of("status", inserted ? "inserted" : "duplicate_log_id");
    }
}
