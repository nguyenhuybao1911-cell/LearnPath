package vn.learnpath.repository;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import vn.learnpath.search.SearchService;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.Mockito.mock;

class PathRepositoryTest {
    @Test
    void recommendationConfigAcceptsInstantTimestamp() {
        var repository = new PathRepository(mock(JdbcTemplate.class));
        var result = new SearchService.Result("learner", "target", "reached", List.of(), 1, 1, "ok");

        assertDoesNotThrow(() -> repository.saveRecommendation(
                "learner", "target", result, Map.of("asOf", Instant.parse("2026-10-21T00:00:00Z"))));
    }
}
