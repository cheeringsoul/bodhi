package io.github.cheeringsoul.persistence.dao;

import java.util.List;

public interface DataSource<T> {
    List<T> read();

    void close();
}
