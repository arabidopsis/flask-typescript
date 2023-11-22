# flask-typescript

Typescript for [flask](https://flask.palletsprojects.com/)
based on [FastAPI](https://fastapi.tiangolo.com) and
[pydantic](https://docs.pydantic.dev/) (on which this package depends).

Instead of generating OpenAPI schema, we generate typescript types since
-- we believe --
keeping the client javascript consistent with the backend python is the most
fraught part of web development.

Also, we want to make it easier to send `FormData`
data.

## Install

```python

python -m pip install git+https://git@github.com/arabidopsis/flask-typescript

python -m pip install 'flask-typescript @ git+https://git@github.com/arabidopsis/flask-typescript@<rev>#flask-typescript[sqla]'
```

```python

python -m pip install 'flask-typescript @ git+https://github.com/arabidopsis/flask-typescript@<rev>#flask-typescript[sqla]'
```
or in the `pyproject.toml` file as

flask_typescript = { git = "https://github.com/arabidopsis/flask-typescript.git", branch="main" ,rev = "7df8d83d4cc...." }

## Warning:

Please note that we are trying to ensure synchronization between python and
typescript "types" during an HTTP exchange of data. Because of the hysteresis
between the two languages and the serialisation requirements of JSON:
**only a subset of pydantic/typescript types will ever be supported**.
Keep it simple people -- you'll be happier, I'll be happier :).

## Usage

```python
from flask import Flask
from flask_typescript.api import Api
from pydantic import BaseModel

app = Flask(__name__)
api = Api('name_that_will_appear_in_the_typescript_output')

class User(BaseModel):
    name: str
    age: int

@app.post('/user_ok')
@api # mark this a part of your API
def user_ok(user:User) -> User:
    if user.age > 60:
        return User(name=user.name + ' Jr.', age=20)
    return user

# adds a `ts` subcommmand to flask
api.init_app(app)
```
You can run `flask ts` to generate some typescript types that can help keep your
javascript client code in sync with your python api.

Run  (say) `flask ts typescript > src/types.d.ts`
Then on the client we can do:

```typescript
import type {User} from './types'
async function user_ok(user:User): Promise<User> {
    const resp = await fetch('/user_ok', {
                method:'post',
                body:JSON.stringify(user),
                headers: {
                    "Content-Type": "application/json",
                }
            }
        )
    if (!resp.ok) {
        throw new Error("no good!")
    }
    const reply = await resp.json()
    if (reply.type !== 'success')
        throw new Error("no good!")
    return reply.result as User
}
const user:User = {name:'me', age: 61}
const user2 = await user_ok(user)
user2.age === 20
```



## FormData

```typescript
import type {User} from './types'
async function user_ok(formData:FormData): Promise<User> {
    const resp = await fetch('/user_ok', {
                method:'post',
                body:formData,
            }
        )
    if (!resp.ok) {
        throw new Error("no good!")
    }
    const reply = await resp.json()
    if (reply.type !== 'success')
        throw new Error("no good!")
    return reply.result as User
}
const login = document.forms['login']
login.addEventListener('submit', async (e) => {
    e.preventDefault()
    const user2 = await user_ok(new FormData(login))
})
```

```html
<form name="login">
    name: <input name="name" type="text" required>
    age: <input name="age" type="number" required min="0">
    <button type="submit">Login</button>
</form>
```


## TODO

* Documentation :)
* argument names or no? https://fastapi.tiangolo.com/tutorial/body-multiple-params
* generate [zod](https://zod.dev/) verifiers from pydantic classes ?
* Maybe a flag for deserialsation of [devalue](https://github.com/Rich-Harris/devalue) "json"
  and also reserialsation in this format too?
* Stream responses e.g. ServerSideEvent i.e. responses that are list[BaseModel], Iterator[BaseModel] etc.


It seems a step too far to write the bodies of the fetch functions. You are
going to have to use some sort of `Config = {func_url: url_for('bp.func',...)}` in
a template to connect urls to functions. Unfortunately `app.url_map` only loosely
associates with the original function. `url_defaults` and `url_value_preprocessor` also make things more complicated.
