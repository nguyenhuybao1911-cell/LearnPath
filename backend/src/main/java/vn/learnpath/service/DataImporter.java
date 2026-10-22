package vn.learnpath.service;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.Types;
import java.time.OffsetDateTime;
import java.util.List;

@Service
public class DataImporter {
    @FunctionalInterface
    private interface Binder { void bind(PreparedStatement statement, CSVRecord row) throws Exception; }

    private final JdbcTemplate jdbc;

    public DataImporter(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public long importAll(Path directory) {
        if (!Files.isDirectory(directory)) throw new IllegalArgumentException("Import directory does not exist: " + directory);
        long total = 0;
        total += importFile(directory.resolve("learners.csv"),
                "insert into learner(id) values (?) on conflict(id) do nothing",
                (ps, row) -> ps.setString(1, row.get("id")));
        total += importFile(directory.resolve("concepts.csv"),
                "insert into concept(id,name,field) values (?,?,?) on conflict(id) do update set name=excluded.name, field=excluded.field",
                (ps, row) -> { ps.setString(1, row.get("id")); ps.setString(2, row.get("name")); ps.setString(3, row.get("field")); });
        total += importFile(directory.resolve("problems.csv"),
                "insert into problem(id,title) values (?,?) on conflict(id) do update set title=excluded.title",
                (ps, row) -> { ps.setString(1, row.get("id")); nullableString(ps, 2, row.get("title")); });
        total += importFile(directory.resolve("problem_concepts.csv"),
                "insert into problem_concept(problem_id,concept_id) values (?,?) on conflict do nothing",
                (ps, row) -> { ps.setString(1, row.get("problem_id")); ps.setString(2, row.get("concept_id")); });
        total += importFile(directory.resolve("prerequisites.csv"), """
                insert into prerequisite(prerequisite_id,concept_id,source,ground_truth,text_predict,graph_predict,annotated)
                values (?,?,?,?,?,?,?) on conflict(prerequisite_id,concept_id,source) do update set
                  ground_truth=excluded.ground_truth,text_predict=excluded.text_predict,
                  graph_predict=excluded.graph_predict,annotated=excluded.annotated
                """, (ps, row) -> {
                    ps.setString(1, row.get("prerequisite_id")); ps.setString(2, row.get("concept_id")); ps.setString(3, row.get("source"));
                    nullableInteger(ps, 4, row.get("ground_truth")); nullableDouble(ps, 5, row.get("text_predict"));
                    nullableDouble(ps, 6, row.get("graph_predict")); ps.setBoolean(7, Boolean.parseBoolean(row.get("annotated")));
                });
        total += importFile(directory.resolve("interactions_clean.csv"), """
                insert into interaction(log_id,learner_id,problem_id,is_correct,score,source_attempts,submitted_at,dataset_split)
                values (?,?,?,?,?,?,?,?) on conflict(log_id) do update set learner_id=excluded.learner_id,
                  problem_id=excluded.problem_id,is_correct=excluded.is_correct,score=excluded.score,
                  source_attempts=excluded.source_attempts,submitted_at=excluded.submitted_at,dataset_split=excluded.dataset_split
                """, (ps, row) -> {
                    ps.setString(1, row.get("log_id")); ps.setString(2, row.get("learner_id")); ps.setString(3, row.get("problem_id"));
                    ps.setBoolean(4, Boolean.parseBoolean(row.get("is_correct"))); nullableDouble(ps, 5, row.get("score"));
                    nullableInteger(ps, 6, row.get("source_attempts")); ps.setObject(7, OffsetDateTime.parse(row.get("submitted_at")));
                    ps.setString(8, row.get("dataset_split"));
                });
        total += importFile(directory.resolve("learner_state.csv"), """
                insert into learner_state(learner_id,concept_id,correct_count,total_count,mastery,as_of) values (?,?,?,?,?,?::timestamptz)
                on conflict(learner_id,concept_id,as_of) do update set correct_count=excluded.correct_count,
                  total_count=excluded.total_count,mastery=excluded.mastery
                """, (ps, row) -> {
                    ps.setString(1, row.get("learner_id")); ps.setString(2, row.get("concept_id"));
                    ps.setInt(3, Integer.parseInt(row.get("correct_count"))); ps.setInt(4, Integer.parseInt(row.get("total_count")));
                    ps.setDouble(5, Double.parseDouble(row.get("mastery"))); ps.setString(6, row.get("as_of"));
                });
        total += importFile(directory.resolve("concept_difficulty.csv"), """
                insert into concept_difficulty(concept_id,train_correct,train_total,difficulty,derived_from_split) values (?,?,?,?,?)
                on conflict(concept_id) do update set train_correct=excluded.train_correct,train_total=excluded.train_total,
                  difficulty=excluded.difficulty,derived_from_split=excluded.derived_from_split
                """, (ps, row) -> {
                    ps.setString(1, row.get("concept_id")); ps.setInt(2, Integer.parseInt(row.get("train_correct")));
                    ps.setInt(3, Integer.parseInt(row.get("train_total"))); ps.setDouble(4, Double.parseDouble(row.get("difficulty")));
                    ps.setString(5, row.get("derived_from_split"));
                });
        total += importFile(directory.resolve("data_summary.csv"),
                "insert into data_summary(key,value) values (?,?::jsonb) on conflict(key) do update set value=excluded.value",
                (ps, row) -> { ps.setString(1, row.get("key")); ps.setString(2, row.get("value")); });
        return total;
    }

    private long importFile(Path path, String sql, Binder binder) {
        if (!Files.isRegularFile(path)) throw new IllegalArgumentException("Missing import file: " + path);
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            reader.mark(1);
            if (reader.read() != '\uFEFF') reader.reset();
            try (CSVParser parser = CSVParser.parse(reader,
                    CSVFormat.DEFAULT.builder().setHeader().setSkipHeaderRecord(true).build())) {
                return jdbc.execute((ConnectionCallback<Long>) connection -> {
                    try (PreparedStatement statement = connection.prepareStatement(sql)) {
                        long count = 0;
                        int pending = 0;
                        for (CSVRecord row : parser) {
                            binder.bind(statement, row);
                            statement.addBatch();
                            count++;
                            if (++pending == 1000) { statement.executeBatch(); pending = 0; }
                        }
                        if (pending > 0) statement.executeBatch();
                        return count;
                    } catch (Exception error) {
                        throw new IllegalStateException("Import failed at " + path, error);
                    }
                });
            }
        } catch (IOException error) {
            throw new IllegalStateException("Unable to read CSV: " + path, error);
        }
    }

    private void nullableString(PreparedStatement ps, int index, String value) throws Exception {
        if (value == null || value.isEmpty()) ps.setNull(index, Types.VARCHAR); else ps.setString(index, value);
    }
    private void nullableInteger(PreparedStatement ps, int index, String value) throws Exception {
        if (value == null || value.isEmpty()) ps.setNull(index, Types.INTEGER); else ps.setInt(index, Integer.parseInt(value));
    }
    private void nullableDouble(PreparedStatement ps, int index, String value) throws Exception {
        if (value == null || value.isEmpty()) ps.setNull(index, Types.DOUBLE); else ps.setDouble(index, Double.parseDouble(value));
    }
}
