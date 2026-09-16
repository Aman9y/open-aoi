# Contributing to open-aoi

First off, thank you for considering contributing to open-aoi! It's people like you that make open-source tools great. 

## Where do I go from here?

If you've noticed a bug or have a feature request, make sure to check our [Issues](../../issues) to see if someone else has already created a ticket. If not, go ahead and make one!

## Setting up for Local Development

To work on the project locally, you will need **Python 3.10+** and **Node.js 18+**.

1. **Fork the repository** and clone it locally.
2. **Setup the Backend (Python):**
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate | Mac/Linux: source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```
3. **Setup the Frontend (React/Vite):**
   ```bash
   cd frontend
   npm install
   ```

Check out the `SETUP.md` and `ARCHITECTURE.md` files for deeper technical context on how the camera pipelines and ML models are structured.

## Pull Request Process

1. Ensure any install or build dependencies are removed before the end of the layer when doing a build.
2. Update the README.md with details of changes to the interface or architecture if applicable.
3. Make sure your code passes the CI checks (our GitHub actions run `pytest` for the backend and `npm run build` for the frontend).
4. Fill out the provided Pull Request template when submitting.

Once you submit your PR, a maintainer will review your code. We might ask for some changes, but don't worry—we are here to help!

## Our Contributors

Thank you to everyone who has helped build `open-aoi`! 

[![Contributors](https://contrib.rocks/image?repo=Aman9y/open-aoi)](https://github.com/Aman9y/open-aoi/graphs/contributors)
