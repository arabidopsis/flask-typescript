(function () {
    const form = document.getElementById('myform')
    const result = document.getElementById('result')

    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        result.textContent = ''
        const formData = new FormData(form)
        console.log('any checked?', 'checked' in formData)
        for (const [key, value] of formData) {
            result.textContent += `${key}: ${value}\n`;
        }
        try {
            const resp = await fetch(form.action, { method: 'post', body: formData })
            const json = await resp.json()
            console.log(resp.ok, resp.status === 200, json)

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
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/json', { method: 'post' })
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        //await getit(form.action, new FormData(form))
    })
})()


async function serializeFormData(formData) {
    const obj = {}

    for (const [key, value] of formData.entries()) {
        if (!(value instanceof File)) {
            const o = obj[key]
            if (o === undefined) {
                obj[key] = value;
            } else if (Array.isArray(o)) {
                o.push(value)
            } else {
                obj[key] = [o, value]
            }
        } else {
            obj[key] = await value.text()
        }
    }
    return obj;
};
