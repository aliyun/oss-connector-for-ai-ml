package com.aliyun.lance.osstables;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.lance.namespace.LanceNamespace;
import org.lance.namespace.model.CreateNamespaceRequest;
import org.lance.namespace.model.DeclareTableRequest;
import org.lance.namespace.model.DeregisterTableRequest;
import org.lance.namespace.model.DescribeNamespaceRequest;
import org.lance.namespace.model.DescribeTableRequest;
import org.lance.namespace.model.DropNamespaceRequest;
import org.lance.namespace.model.DropTableRequest;
import org.lance.namespace.model.ListNamespacesRequest;
import org.lance.namespace.model.ListTablesRequest;
import org.lance.namespace.model.NamespaceExistsRequest;
import org.lance.namespace.model.RenameTableRequest;
import org.lance.namespace.model.TableExistsRequest;

/**
 * W12 live coverage: exercise the catalog-only APIs directly through the Java SDK against a live
 * OssTables endpoint. Records PASS/FAIL per API into a summary printed to stdout. Skipped unless
 * OSSTABLE_URI etc. are present in the environment.
 */
class JavaApiCoverageIT {

  private static String env(String k) {
    return System.getenv(k);
  }

  private LanceNamespace connectLive() {
    String uri = env("OSSTABLE_URI");
    Assumptions.assumeTrue(uri != null && !uri.isEmpty(), "OSSTABLE_URI not set — skipping live test");
    Map<String, String> props = new HashMap<>();
    props.put(OssTablesNamespace.PROPERTY_URI, uri);
    props.put(SigV4Signer.PROPERTY_REGION, env("OSSTABLE_REGION"));
    props.put(SigV4Signer.PROPERTY_SERVICE, env("OSSTABLE_SERVICE") == null ? "osstables" : env("OSSTABLE_SERVICE"));
    props.put(SigV4Signer.PROPERTY_ACCESS_KEY_ID, env("OSSTABLE_AK"));
    props.put(SigV4Signer.PROPERTY_SECRET_ACCESS_KEY, env("OSSTABLE_SK"));
    props.put(OssTablesNamespace.PROPERTY_VERIFY_SSL, "false");
    return LanceNamespace.connect("com.aliyun.lance.osstables.OssTablesNamespace", props, null);
  }

  @Test
  void catalogApiCoverage() {
    LanceNamespace ns = connectLive();
    String db = "w12java_" + (System.currentTimeMillis() / 1000);
    List<String> nsId = Arrays.asList(db);
    Map<String, String> results = new LinkedHashMap<>();
    List<String> failures = new ArrayList<>();

    run(results, failures, "1.namespaceId", () -> {
      String id = ns.namespaceId();
      require(id != null, "namespaceId null");
      return id;
    });

    run(results, failures, "2.createNamespace", () -> {
      CreateNamespaceRequest r = new CreateNamespaceRequest();
      r.setId(nsId);
      ns.createNamespace(r);
      return "created " + db;
    });

    run(results, failures, "3.namespaceExists(true)", () -> {
      NamespaceExistsRequest r = new NamespaceExistsRequest();
      r.setId(nsId);
      ns.namespaceExists(r);
      return "exists";
    });

    run(results, failures, "4.describeNamespace", () -> {
      DescribeNamespaceRequest r = new DescribeNamespaceRequest();
      r.setId(nsId);
      Object resp = ns.describeNamespace(r);
      return resp == null ? "null-resp" : "ok";
    });

    run(results, failures, "5.listNamespaces", () -> {
      ListNamespacesRequest r = new ListNamespacesRequest();
      r.setId(new ArrayList<>());
      Object resp = ns.listNamespaces(r);
      return resp == null ? "null" : "ok";
    });

    List<String> tid = Arrays.asList(db, "t_java");
    run(results, failures, "6.declareTable", () -> {
      DeclareTableRequest r = new DeclareTableRequest();
      r.setId(tid);
      Object resp = ns.declareTable(r);
      return resp == null ? "null-resp" : "declared";
    });

    run(results, failures, "7.tableExists(true)", () -> {
      TableExistsRequest r = new TableExistsRequest();
      r.setId(tid);
      ns.tableExists(r);
      return "exists";
    });

    run(results, failures, "8.describeTable", () -> {
      DescribeTableRequest r = new DescribeTableRequest();
      r.setId(tid);
      r.setWithTableUri(true);
      Object resp = ns.describeTable(r);
      return resp == null ? "null-resp" : "ok";
    });

    run(results, failures, "9.listTables", () -> {
      ListTablesRequest r = new ListTablesRequest();
      r.setId(nsId);
      Object resp = ns.listTables(r);
      return resp == null ? "null" : resp.toString().substring(0, Math.min(80, resp.toString().length()));
    });

    List<String> tid2 = Arrays.asList(db, "t_java_renamed");
    run(results, failures, "10.renameTable", () -> {
      RenameTableRequest r = new RenameTableRequest();
      r.setId(tid);
      r.setNewTableName("t_java_renamed");
      ns.renameTable(r);
      return "renamed";
    });

    run(results, failures, "11.deregisterTable", () -> {
      DeregisterTableRequest r = new DeregisterTableRequest();
      r.setId(tid2);
      ns.deregisterTable(r);
      return "deregistered";
    });

    // re-declare to have something to hard-drop
    run(results, failures, "12.declareTable(again)", () -> {
      DeclareTableRequest r = new DeclareTableRequest();
      r.setId(Arrays.asList(db, "t_drop"));
      ns.declareTable(r);
      return "declared t_drop";
    });

    run(results, failures, "13.dropTable", () -> {
      DropTableRequest r = new DropTableRequest();
      r.setId(Arrays.asList(db, "t_drop"));
      ns.dropTable(r);
      return "dropped";
    });

    run(results, failures, "14.dropNamespace", () -> {
      DropNamespaceRequest r = new DropNamespaceRequest();
      r.setId(nsId);
      ns.dropNamespace(r);
      return "dropped ns";
    });

    System.out.println("\n===== JAVA API COVERAGE =====");
    results.forEach((k, v) -> System.out.println("  " + k + " -> " + v));
    System.out.println("PASS " + (results.size() - failures.size()) + "/" + results.size());
    if (!failures.isEmpty()) {
      System.out.println("FAILURES: " + failures);
    }
    // Do not hard-fail the build on optional-API differences; surface via stdout.
    // But fail if a core recommended op broke.
    for (String core : new String[] {"2.createNamespace", "6.declareTable", "8.describeTable",
        "9.listTables", "13.dropTable", "14.dropNamespace"}) {
      org.junit.jupiter.api.Assertions.assertFalse(
          failures.contains(core), "core API failed: " + core);
    }
  }

  private interface Call {
    String run() throws Exception;
  }

  private static void require(boolean cond, String msg) {
    if (!cond) throw new RuntimeException(msg);
  }

  private static void run(Map<String, String> results, List<String> failures, String name, Call c) {
    try {
      results.put(name, "PASS: " + c.run());
    } catch (Throwable t) {
      results.put(name, "FAIL: " + t.getClass().getSimpleName() + ": "
          + String.valueOf(t.getMessage()).replaceAll("\\s+", " "));
      failures.add(name);
    }
  }
}
