package vn.learnpath.search;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class SearchServiceTest {
    private final SearchService search = new SearchService();
    private final SearchService.Settings settings = new SearchService.Settings(
            0.7, 2, new SearchService.Weights(0, .35, .25, .40), 100, Duration.ofSeconds(1), Set.of());

    @Test
    void targetAlreadyMasteredIsDifferentFromUnknownTarget() {
        var concepts = Map.of("a", new SearchService.Concept("a", "A"));
        var mastered = search.recommend("u", "a", concepts, List.of(), Map.of("a", new SearchService.Mastery(2, 2)), Map.of(), settings);
        var unknown = search.recommend("u", "a", concepts, List.of(), Map.of(), Map.of(), settings);
        assertEquals("target_already_mastered", mastered.status());
        assertEquals("reached", unknown.status());
        assertEquals("a", unknown.steps().getFirst().conceptId());
    }

    @Test
    void keepsAlternativeBranchesAndRequiresEveryPrerequisite() {
        var concepts = Map.of("a", new SearchService.Concept("a", "A"), "b", new SearchService.Concept("b", "B"), "t", new SearchService.Concept("t", "Target"));
        var edges = List.of(new SearchService.Edge("a", "t"), new SearchService.Edge("b", "t"));
        var result = search.recommend("u", "t", concepts, edges, Map.of(), Map.of(), settings);
        assertEquals("reached", result.status());
        assertEquals(Set.of("a", "b", "t"), result.steps().stream().map(SearchService.Step::conceptId).collect(java.util.stream.Collectors.toSet()));
        assertTrue(result.peakOpen() > 1);
        assertTrue(result.steps().getLast().scores().p() == 1.0);
    }

    @Test
    void rejectsCyclesAndReportsScopeAndBudgetFailures() {
        var concepts = Map.of("a", new SearchService.Concept("a", "A"), "b", new SearchService.Concept("b", "B"));
        assertThrows(IllegalArgumentException.class, () -> search.recommend("u", "a", concepts,
                List.of(new SearchService.Edge("a", "b"), new SearchService.Edge("b", "a")), Map.of(), Map.of(), settings));
        var missing = search.recommend("u", "b", concepts, List.of(), Map.of(), Map.of(), new SearchService.Settings(.7, 2,
                settings.weights(), 20, Duration.ofSeconds(1), Set.of("a")));
        assertEquals("no_path", missing.status());
        var limitedConcepts = Map.of("a", new SearchService.Concept("a", "A"), "b", new SearchService.Concept("b", "B"), "t", new SearchService.Concept("t", "T"));
        var limited = search.recommend("u", "t", limitedConcepts, List.of(new SearchService.Edge("a", "t"), new SearchService.Edge("b", "t")), Map.of(), Map.of(), new SearchService.Settings(.7, 2,
                settings.weights(), 1, Duration.ofSeconds(1), Set.of()));
        assertEquals("budget_exhausted", limited.status());
    }
}
