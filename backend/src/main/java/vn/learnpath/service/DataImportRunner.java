package vn.learnpath.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import java.nio.file.Path;

@Component
public class DataImportRunner implements ApplicationRunner {
    private final DataImporter importer;
    @Value("${app.import-dir:}") private String importDirectory;

    public DataImportRunner(DataImporter importer) { this.importer = importer; }

    @Override
    public void run(ApplicationArguments args) {
        if (importDirectory == null || importDirectory.isBlank()) return;
        long rows = importer.importAll(Path.of(importDirectory));
        System.out.println("LearnPath data import complete; CSV rows processed: " + rows);
    }
}
