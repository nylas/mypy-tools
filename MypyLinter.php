<?php

final class MypyLinter extends ArcanistLinter {

  private $seen_errors = array();
  private $paths_to_lint = array();
  private $errors_to_show = array();
  private $printed_mypy_server_error = false;
  private $config = null;

  private function getConfig() {
    if ($this->config !== null) {
      return $this->config;
    }
    $config_path = join(DIRECTORY_SEPARATOR, array($this->getProjectRoot(), '.mypy_server'));
    $config_contents = file_get_contents($config_path);
    if ($config_contents === false) {
      throw new RuntimeException("Config file not found: $config_path");
    }
    $this->config = json_decode($config_contents, true);
    return $this->config;
  }

  public function getLinterName() {
    return 'MypyLinter ';
  }

  public function getLintNameMap() {
    return array(
      'typecheck_error' => 'Typecheck error',
      'mypy_missing' => 'Mypy not found',
      'missing_mypy_annotation' => 'Please add a mypy annotation!',
    );
  }

  private function checkMypyAnnotations() {
    exec("check_mypy_annotations.py master", $output);
    foreach ($output as $line) {
      if (array_key_exists($line, $this->seen_errors)) {
        continue;
      }

      $filename = null;
      $lineNumber = null;

      $matches = array();
      if (preg_match('/^(.+):(\d+) Please add a mypy annotation!$/', $line, $matches) === 1) {
        $filename = $matches[1];
        $lineNumber = $matches[2];
      }

      if (array_key_exists($filename, $this->errors_to_show)) {
        $this->errors_to_show[$filename][] = ['missing_mypy_annotation', $lineNumber];
      } else {
        $this->errors_to_show[$filename] = [['missing_mypy_annotation', $lineNumber]];
      }
      $this->seen_errors[$line] = true;
    }
  }

  /**
   * Hook called before a list of paths are linted.
   *
   * Parallelizable linters can start multiple requests in parallel here,
   * to improve performance. They can implement @{method:didLintPaths} to
   * collect results.
   *
   * Linters which are not parallelizable should normally ignore this callback
   * and implement @{method:lintPath} instead.
   *
   * @param list<string> A list of paths to be linted
   * @return void
   * @task exec
   */
  public function willLintPaths(array $paths) {
    $this->checkMypyAnnotations();
    foreach ($paths as $path) {
      $this->paths_to_lint[$path] = true;
    }
  }

  private function shouldUseStrictOptional($absPath) {
    $strictDirectories = array();
    foreach ($this->getConfig()['src_dirs'] as $src_dir) {
      if (!isset($src_dir['strict_optional'])) {
        continue;
      }
      // The last empty string is so we append a slash onto the end, thus avoiding matching prefixes.
      $strictDir = join(DIRECTORY_SEPARATOR, array($this->getProjectRoot(), $src_dir['path'], ''));
      if (0 === strpos($absPath, $strictDir)) {
        return true;
      }
    }
    return false;
  }

  public function getMissingMypyOutput($absPath) {
    $mypy_path_parts = array_map(function($part) {
      return join(DIRECTORY_SEPARATOR, array($this->getProjectRoot(), $part));
    }, $this->getConfig()['mypy_path']);
    $mypy_path = join(PATH_SEPARATOR, $mypy_path_parts);

    $strictOptional = "";
    if ($this->shouldUseStrictOptional($absPath)) {
      $strictOptional = "--strict-optional";
    }

    $flags = join(' ', $this->getConfig()['global_flags']);
    exec("MYPYPATH=$mypy_path mypy $flags $strictOptional $absPath 2>&1", $output);
    return $output;
  }

  public function getMypyOutput($absPath) {
    $output = array();
    $fileNameHash = md5($absPath);
    $fileContentHash = md5(file_get_contents($absPath));
    $port = $this->getConfig()['port'];
    $url = "http://localhost:$port/file/$fileNameHash/$fileContentHash";

    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    $content = curl_exec($ch);

    if ($content === FALSE) {
      curl_close($ch);

      if (!$this->printed_mypy_server_error) {
        $msg = "
\033[1mWARNING\033[0m: It looks like you're not running the mypy server.  Doing so
         could significantly speed up arc lint. Simply run `\033[1mmypy_server.py\033[0m`
         in another terminal :-)\n\n";
        echo $msg;
        $this->printed_mypy_server_error = true;
      }

      return $this->getMissingMypyOutput($absPath);
    }

    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($httpCode !== 200) {
      return $this->getMissingMypyOutput($absPath);
    }

    $obj = json_decode($content);
    $output_str = $obj->output;
    $output = explode("\n", $output_str);
    return $output;
  }

  /**
   * Hook called for each path to be linted.
   *
   * Linters which are not parallelizable can do work here.
   *
   * Linters which are parallelizable may want to ignore this callback and
   * implement @{method:willLintPaths} and @{method:didLintPaths} instead.
   *
   * @param string Path to lint.
   * @return void
   * @task exec
   */
  public function lintPath($path) {
    $output = array();
    $absPath = join(DIRECTORY_SEPARATOR, array($this->getProjectRoot(), $path));

    $output = $this->getMypyOutput($absPath);

    if (count($output) > 0 && preg_match('/command not found/', $output[0]) === 1) {
      $this->raiseLintAtPath('mypy_missing', 'Please install mypy first! See: http://mypy.readthedocs.io/en/latest/getting_started.html#installation');
      return;
    }

    if (array_key_exists($absPath, $this->errors_to_show)) {
      foreach ($this->errors_to_show[$absPath] as $entry) {
        $errorType = $entry[0];
        $lineNumber = $entry[1];

        $this->raiseLintAtLine($lineNumber, null, $errorType, '');
      }
    }

    foreach ($output as $line) {
      if (array_key_exists($line, $this->seen_errors)) {
        continue;
      }

      $filename = null;
      $lineNumber = null;

      $matches = array();
      if (preg_match('/(.+):(\d+):\serror:\s(.*)$/', $line, $matches) === 1) {
        $filename = $matches[1];
        $lineNumber = $matches[2];
        $error = $matches[3];
      } else {
        continue;
      }

      if ($filename === $this->getActivePath()) {
        $this->raiseLintAtLine($lineNumber, null, 'typecheck_error', $error);
      } else if (array_key_exists($filename, $this->paths_to_lint)) {
        // We're going to revisit this error later when we lint the file where
        // actual the error occurs. We want to show the error with more context
        // where it actually happens, and we don't want duplicates, so just skip
        // the error for now without marking it as seen.
        continue;
      } else {
        $this->raiseLintAtPath('typecheck_error', $line);
      }

      $this->seen_errors[$line] = true;
    }
  }
}

