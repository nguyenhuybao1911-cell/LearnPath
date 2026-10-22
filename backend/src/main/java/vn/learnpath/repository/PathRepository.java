package vn.learnpath.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import vn.learnpath.search.SearchService;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;

@Repository
public class PathRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();

    public PathRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public List<String> learners() {
        return jdbc.query("select id from learner order by id limit 500", (rs, row) -> rs.getString(1));
    }

    public List<SearchService.Concept> concepts() {
        return jdbc.query("select id, name from concept order by name, id",
                (rs, row) -> new SearchService.Concept(rs.getString("id"), rs.getString("name")));
    }

    public Map<String, SearchService.Concept> conceptMap() {
        Map<String, SearchService.Concept> result = new LinkedHashMap<>();
        for (var concept : concepts()) result.put(concept.id(), concept);
        return result;
    }

    public List<SearchService.Edge> prerequisites() {
        return jdbc.query("select prerequisite_id, concept_id from prerequisite where annotated = true and ground_truth = 1 order by prerequisite_id, concept_id",
                (rs, row) -> new SearchService.Edge(rs.getString(1), rs.getString(2)));
    }

    public Map<String, SearchService.Mastery> mastery(String learnerId, Instant before) {
        String sql = """
                select pc.concept_id,
                       sum(case when i.is_correct then 1 else 0 end)::integer as correct_count,
                       count(*)::integer as total_count
                from interaction i join problem_concept pc on pc.problem_id = i.problem_id
                where i.learner_id = ? and i.submitted_at < ?
                group by pc.concept_id
                """;
        Map<String, SearchService.Mastery> result = new HashMap<>();
        jdbc.query(sql, rs -> { result.put(rs.getString(1), new SearchService.Mastery(rs.getInt(2), rs.getInt(3))); }, learnerId, Timestamp.from(before));
        return result;
    }

    public Map<String, Double> trainDifficulty() {
        String sql = """
                select pc.concept_id,
                       1.0 - avg(case when i.is_correct then 1.0 else 0.0 end) as difficulty
                from interaction i join problem_concept pc on pc.problem_id = i.problem_id
                where i.dataset_split = 'train'
                group by pc.concept_id
                """;
        Map<String, Double> result = new HashMap<>();
        jdbc.query(sql, rs -> { result.put(rs.getString(1), rs.getDouble(2)); });
        return result;
    }

    public boolean addInteraction(String learnerId, String problemId, String logId, boolean correct, Double score,
                                  Integer sourceAttempts, Instant submittedAt) {
        jdbc.update("insert into learner(id) values (?) on conflict do nothing", learnerId);
        return jdbc.update("""
                insert into interaction(log_id, learner_id, problem_id, is_correct, score, source_attempts, submitted_at)
                values (?, ?, ?, ?, ?, ?, ?) on conflict (log_id) do nothing
                """, logId, learnerId, problemId, correct, score, sourceAttempts, Timestamp.from(submittedAt)) == 1;
    }

    public void saveRecommendation(String learnerId, String targetId, SearchService.Result result, Object config) {
        UUID id = UUID.randomUUID();
        jdbc.update("insert into recommendation(id, learner_id, target_id, status, config) values (?, ?, ?, ?, ?::jsonb)",
                id, learnerId, targetId, result.status(), toJson(config));
        for (int index = 0; index < result.steps().size(); index++) {
            var step = result.steps().get(index);
            jdbc.update("insert into recommendation_step(recommendation_id, step_index, concept_id, scores) values (?, ?, ?, ?::jsonb)",
                    id, index + 1, step.conceptId(), toJson(step.scores()));
        }
    }

    private String toJson(Object value) {
        try { return json.writeValueAsString(value); }
        catch (JsonProcessingException error) { throw new IllegalStateException("Unable to store recommendation", error); }
    }

    public long conceptCount() { return jdbc.queryForObject("select count(*) from concept", Long.class); }
}
