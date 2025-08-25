package io.github.cheeringsoul.persistence.datasource;

import java.util.List;

public interface DataSource<T> {
    List<T> read();

    void close();
}
