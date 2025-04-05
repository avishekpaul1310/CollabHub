# Contributing to CollabHub

## Welcome Contributors!

First off, thank you for considering contributing to CollabHub. It's people like you that make CollabHub such a great collaboration platform.

### Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all contributors. Our project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md), and participants are expected to uphold this code.

## How Can You Contribute?

There are many ways to contribute to CollabHub:

### 1. Reporting Bugs
- Use the GitHub Issues section
- Check existing issues to avoid duplicates
- Provide a clear and descriptive title
- Describe the exact steps to reproduce the problem
- Include your operating system, Python version, and Django version

#### Bug Report Template:
```markdown
**Describe the bug:**
A clear description of what the bug is.

**To Reproduce:**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior:**
A clear description of what you expected to happen.

**Screenshots:**
If applicable, add screenshots to help explain the problem.

**Environment:**
 - OS: [e.g., Ubuntu 20.04]
 - Python Version: [e.g., 3.8.5]
 - Django Version: [e.g., 4.2.7]
 - CollabHub Version: [e.g., 1.0.0]
```

### 2. Suggesting Enhancements
- Open a GitHub Issue with a clear title
- Provide detailed description of the enhancement
- Explain why this feature would be useful
- Include mockups or diagrams if possible

### 3. Development Process

#### Setting Up Development Environment
1. Fork the repository
2. Clone your fork
```bash
git clone https://github.com/YOUR_USERNAME/CollabHub.git
cd CollabHub
```

3. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

4. Install development dependencies
```bash
pip install -r requirements-dev.txt
```

5. Create a new branch for your feature
```bash
git checkout -b feature/your-feature-name
```

#### Development Guidelines
- Follow PEP 8 style guidelines
- Write comprehensive tests for new features
- Ensure all tests pass before submitting a pull request
- Use type hints
- Write clear, concise docstrings
- Maintain consistent code formatting

#### Commit Message Guidelines
- Use clear and descriptive commit messages
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")

Example:
```
Add user authentication middleware

- Implement JWT-based authentication
- Add login and logout views
- Create user permission decorators
```

### 4. Pull Request Process
1. Ensure your code passes all tests
2. Update documentation accordingly
3. Add yourself to CONTRIBUTORS.md
4. Your pull request will be reviewed by the maintainers

#### Pull Request Template:
```markdown
## Description
[Provide a detailed description of your changes]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
[Describe the tests that you ran to verify your changes]

## Checklist:
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective
```

### 5. Security Vulnerabilities
- Do NOT open Issues for security vulnerabilities
- Email avishek-paul@outlook.com with details
- Include steps to reproduce and potential impact
- Do not share publicly until the issue is resolved

### 6. Questions and Support
- Use GitHub Discussions for questions
- Check existing discussions before creating a new one
- Be respectful and patient

## Recognition
Contributors will be recognized in our CONTRIBUTORS.md file and potentially in release notes.

## Licensing
By contributing, you agree that your contributions will be licensed under the project's existing license.

---

Thank you for your interest in making CollabHub better! 

Best regards,
The CollabHub Team
