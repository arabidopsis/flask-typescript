# Development

## Install

```python

python -m pip install git+https://git@github.com/arabidopsis/flask-typescript

python -m pip install 'flask-typescript @ git+https://git@github.com/arabidopsis/flask-typescript@<rev>#flask-typescript[sqlalchemy]'
```

```python

python -m pip install 'flask-typescript @ git+https://github.com/arabidopsis/flask-typescript@<rev>#flask-typescript[sqlalchemy]'
```

or in the `pyproject.toml` file as

flask_typescript = { git = "https://github.com/arabidopsis/flask-typescript.git", branch="main" ,rev = "7df8d83d4cc...." }

## TODO

- Documentation :)
- argument names or no? https://fastapi.tiangolo.com/tutorial/body-multiple-params
- generate [zod](https://zod.dev/) verifiers from pydantic classes ?
- Maybe a flag for deserialsation of [devalue](https://github.com/Rich-Harris/devalue) "json"
  and also reserialsation in this format too?
- Stream responses e.g. ServerSideEvent i.e. responses that are list[BaseModel], Iterator[BaseModel] etc.

It seems a step too far to write the bodies of the fetch functions.
