(function () {
    const form = document.getElementById('myform')
    const result = document.getElementById('result')
    const json_result = document.getElementById('result-json')

    form.addEventListener('submit', async (e) => {
        // e.stopPropagation()
        result.textContent = ''
        const formData = new FormData(form)
        for (const [key, value] of formData) {
            result.textContent += `${key}: ${value}\n`;
        }

        console.log('any checked?', formData.has('checked'))

        e.preventDefault()
        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            json_result.textContent = JSON.stringify(json)
            console.log(resp.ok, json, new Date(json.date))

            // as json
            const obj = JSON.stringify(await serializeFormData(formData))
            const resp1 = await fetch(form.action, {
                method: 'post',
                body: obj,
                headers: {
                    "Content-Type": "application/json",
                }
            })
            const json1 = await resp1.json()
            console.log(resp1.ok, json1)
        } catch (e) {
            console.log('err', e)
        }

    })




    const json1 = document.getElementById('json1')
    const result1 = document.getElementById('json1-result')
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/json', { method: 'post' })
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        result1.textContent = JSON.stringify(json)
    })
})();

(function () {
    const form = document.getElementById('filestorage')
    const result = document.getElementById('filestorage-result')


    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        const formData = new FormData(form)

        // this works with a File object

        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            console.log(resp.ok, resp.status === 200, json)
            result.textContent = JSON.stringify(json)
        } catch (e) {
            console.log('err', e)
        }

    })

})();

async function serializeFormData(formData) {
    const obj = {}

    async function cvt(value) {
        if (value instanceof File) {
            return await value.text()
        }
        return value
    }

    for (let [key, value] of formData) {
        const o = obj[key]
        value = await cvt(value)
        if (o === undefined) {
            obj[key] = value;
        } else if (Array.isArray(o)) {
            o.push(value)
        } else {
            obj[key] = [o, value]
        }

    }
    return obj;
};
