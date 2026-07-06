class Aira < Formula
  include Language::Python::Virtualenv

  desc "Static analysis for AI-generated code failure patterns"
  homepage "https://aira.bageltech.net"
  url "https://github.com/BDB-Labs/aira-scanner/archive/refs/tags/v1.3.0.tar.gz"
  version "1.3.0"
  sha256 "ebd380727dee25a18ce21eb0bc4a8de6ee2a1b266e677e6ab51984ba5e4593c9"
  license "MIT"
  head "https://github.com/BDB-Labs/aira-scanner.git", branch: "main"

  depends_on "libyaml"
  depends_on "python@3.13"

  resource "setuptools" do
    url "https://files.pythonhosted.org/packages/4f/db/cfac1baf10650ab4d1c111714410d2fbb77ac5a616db26775db562c8fab2/setuptools-82.0.1.tar.gz"
    sha256 "7d872682c5d01cfde07da7bccc7b65469d3dca203318515ada1de5eda35efbf9"
  end

  resource "wheel" do
    url "https://files.pythonhosted.org/packages/89/24/a2eb353a6edac9a0303977c4cb048134959dd2a51b48a269dfc9dde00c8a/wheel-0.46.3.tar.gz"
    sha256 "e3e79874b07d776c40bd6033f8ddf76a7dad46a7b8aa1b2787a83083519a1803"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz"
    sha256 "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
  end

  def install
    venv = virtualenv_create(libexec, "python3.13")
    venv.pip_install [resource("setuptools"), resource("wheel"), resource("pyyaml")]

    system libexec/"bin/python", "-m", "pip", "install",
           "--no-deps",
           "--no-build-isolation",
           buildpath/"CLI"

    bin.install_symlink libexec/"bin/aira"
  end

  test do
    (testpath/"sample.py").write <<~PYTHON
      try:
          risky()
      except Exception:
          pass
    PYTHON

    output = shell_output("#{bin}/aira scan #{testpath}/sample.py --output json --fail-on none")
    assert_match "\"check_id\": \"C03\"", output
  end
end
